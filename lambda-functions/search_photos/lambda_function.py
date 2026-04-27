"""
LF2 — search-photos
Wired to GET /search?q={query} via API Gateway Lambda-proxy integration.
  1. Pull q from query params
  2. Call Lex V2 RecognizeText to disambiguate keywords
  3. Read SearchIntent slot values (keyword1, keyword2)
  4. If any keywords, run terms query against OpenSearch "photos" index
  5. Return {results: [{url, labels}]} (empty array if no keywords)
"""

import json
import os
import uuid

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import Session as BotoSession
from urllib3 import PoolManager

REGION = os.environ.get("AWS_REGION", "us-east-1")
ES_ENDPOINT = os.environ["ES_ENDPOINT"].rstrip("/")
ES_INDEX = os.environ.get("ES_INDEX", "photos")
LEX_BOT_ID = os.environ["LEX_BOT_ID"]
LEX_BOT_ALIAS_ID = os.environ["LEX_BOT_ALIAS_ID"]
LEX_LOCALE_ID = os.environ.get("LEX_LOCALE_ID", "en_US")
PHOTOS_BUCKET = os.environ["PHOTOS_BUCKET"]

lex = boto3.client("lexv2-runtime", region_name=REGION)
http = PoolManager()
_credentials = BotoSession().get_credentials()

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type, x-api-key",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
}


def _resp(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": CORS_HEADERS, "body": json.dumps(body)}


def _signed_es_post(path: str, body: dict) -> dict:
    url = f"{ES_ENDPOINT}{path}"
    payload = json.dumps(body).encode("utf-8")
    req = AWSRequest(method="POST", url=url, data=payload,
                     headers={"Content-Type": "application/json"})
    SigV4Auth(_credentials, "es", REGION).add_auth(req)
    resp = http.request("POST", url, body=payload, headers=dict(req.headers))
    if resp.status >= 300:
        raise RuntimeError(f"OpenSearch query failed {resp.status}: {resp.data.decode('utf-8', 'ignore')}")
    return json.loads(resp.data.decode("utf-8"))


def _extract_keywords_via_lex(query: str) -> list[str]:
    """Run text through Lex SearchIntent and pull slot values. Returns [] if Lex finds nothing."""
    if not query.strip():
        return []
    result = lex.recognize_text(
        botId=LEX_BOT_ID,
        botAliasId=LEX_BOT_ALIAS_ID,
        localeId=LEX_LOCALE_ID,
        sessionId=f"search-{uuid.uuid4()}",
        text=query,
    )
    keywords = []
    intent = (result.get("sessionState") or {}).get("intent") or {}
    slots = intent.get("slots") or {}
    for slot_name in ("keyword1", "keyword2"):
        slot = slots.get(slot_name)
        if not slot:
            continue
        # Lex slot value can live in slot["value"]["interpretedValue"] or slot["value"]["originalValue"]
        value = (slot.get("value") or {})
        v = value.get("interpretedValue") or value.get("originalValue")
        if v:
            keywords.append(v.strip().lower())
    # Fallback: if intent didn't bind slots, use raw query split on whitespace (very lenient)
    if not keywords:
        # Strip common stopwords used in utterances
        stop = {"show", "me", "find", "photos", "of", "with", "and", "in", "them", "the", "a"}
        tokens = [t.strip().lower() for t in query.replace(",", " ").split() if t.strip()]
        keywords = [t for t in tokens if t not in stop]
    return keywords[:5]


def _expand_plural(words: list[str]) -> list[str]:
    """Add singular forms for trailing-s plurals so 'dogs' matches the 'dog' label.
    Cheap stemmer — sufficient for class-project-grade query coverage."""
    out = list(words)
    for w in words:
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            singular = w[:-2] if w.endswith("es") and len(w) > 4 else w[:-1]
            if singular and singular not in out:
                out.append(singular)
    return out


def _query_photos(keywords: list[str]) -> list[dict]:
    body = {
        "size": 50,
        "query": {"terms": {"labels": _expand_plural(keywords)}},
    }
    res = _signed_es_post(f"/{ES_INDEX}/_search", body)
    hits = (res.get("hits") or {}).get("hits") or []
    out = []
    for h in hits:
        src = h.get("_source") or {}
        key = src.get("objectKey")
        if not key:
            continue
        out.append({
            "url": f"https://{PHOTOS_BUCKET}.s3.amazonaws.com/{key}",
            "labels": src.get("labels", []),
        })
    return out


def lambda_handler(event, context):
    qs = event.get("queryStringParameters") or {}
    q = (qs.get("q") or "").strip()
    if not q:
        return _resp(200, {"results": []})

    try:
        keywords = _extract_keywords_via_lex(q)
        print(json.dumps({"event": "lex_keywords", "q": q, "keywords": keywords}))
        if not keywords:
            return _resp(200, {"results": []})
        results = _query_photos(keywords)
        return _resp(200, {"results": results})
    except Exception as e:
        print(json.dumps({"event": "error", "message": str(e)}))
        return _resp(500, {"error": str(e), "results": []})
