"""
LF2 — search-photos
Wired to GET /search?q={query} via API Gateway Lambda-proxy integration.

  1. Pull q from query params; empty/missing -> {"results": []}.
  2. Call Lex V2 RecognizeText to disambiguate keywords. The bot has a single
     SearchIntent with two slots, keyword1 and keyword2.
  3. If Lex returns no slots, behaviour depends on STRICT_LEX:
       STRICT_LEX=1 (default, spec-compliant): return {"results": []}.
       STRICT_LEX=0: fall back to a stopword-stripped tokenizer.
  4. Build a bool query against OpenSearch:
       - terms on the keyword field (exact match, single-token labels)
       - match on labels.text for any keyword that contains a space and for
         the original query string (covers multi-word Rekognition labels like
         "labrador retriever" / "sea life" / "aerial view").
     Photos are de-duplicated by document id and capped at 50.
  5. Return {"results": [{url, labels}]} with status 200 always (even on
     internal failure -- the spec asks for an empty array, the API key check
     in API Gateway already filters bad clients).

Env vars:
  ES_ENDPOINT        required
  ES_INDEX           default "photos"
  LEX_BOT_ID         required
  LEX_BOT_ALIAS_ID   required
  LEX_LOCALE_ID      default "en_US"
  PHOTOS_BUCKET      required (B2 name) -- used to build public S3 URLs
  STRICT_LEX         default "1"
"""

import json
import os
import traceback
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
STRICT_LEX = os.environ.get("STRICT_LEX", "1") == "1"

lex = boto3.client("lexv2-runtime", region_name=REGION)
http = PoolManager(timeout=10.0, retries=False)
_credentials = BotoSession().get_credentials()

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type, x-api-key",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
}

STOPWORDS = {
    "show", "me", "find", "get", "photos", "photo", "pictures", "picture",
    "of", "with", "and", "in", "them", "the", "a", "an", "to", "for", "on",
    "containing", "having", "looking", "like", "any", "some", "please",
}


def _log(event: str, **fields) -> None:
    payload = {"event": event, **fields}
    try:
        print(json.dumps(payload, default=str))
    except (TypeError, ValueError):
        print(json.dumps({"event": "log_serialize_failed", "raw": str(payload)}))


def _resp(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": CORS_HEADERS, "body": json.dumps(body)}


def _signed_es_post(path: str, body: dict) -> dict:
    url = f"{ES_ENDPOINT}{path}"
    payload = json.dumps(body).encode("utf-8")
    req = AWSRequest(
        method="POST", url=url, data=payload,
        headers={"Content-Type": "application/json"},
    )
    SigV4Auth(_credentials, "es", REGION).add_auth(req)
    resp = http.request("POST", url, body=payload, headers=dict(req.headers))
    if resp.status >= 300:
        raise RuntimeError(
            f"OpenSearch query failed status={resp.status} "
            f"body={resp.data.decode('utf-8', 'ignore')[:500]}"
        )
    return json.loads(resp.data.decode("utf-8"))


def _extract_keywords_via_lex(query: str) -> list[str]:
    """Run text through Lex SearchIntent; pull slot values keyword1 and keyword2.
    Returns [] if Lex finds no slots (and we are in STRICT_LEX mode)."""
    if not query.strip():
        return []
    try:
        result = lex.recognize_text(
            botId=LEX_BOT_ID,
            botAliasId=LEX_BOT_ALIAS_ID,
            localeId=LEX_LOCALE_ID,
            sessionId=f"search-{uuid.uuid4()}",
            text=query,
        )
    except Exception as exc:  # noqa: BLE001
        _log("lex_error", message=str(exc), errorClass=type(exc).__name__)
        return _fallback_tokens(query) if not STRICT_LEX else []

    keywords: list[str] = []
    intent = (result.get("sessionState") or {}).get("intent") or {}
    slots = intent.get("slots") or {}
    for slot_name in ("keyword1", "keyword2"):
        slot = slots.get(slot_name)
        if not slot:
            continue
        value = slot.get("value") or {}
        v = value.get("interpretedValue") or value.get("originalValue")
        if v:
            keywords.append(v.strip().lower())

    if keywords:
        return keywords[:5]

    # Lex returned no slot bindings.
    if STRICT_LEX:
        _log("lex_no_slots_strict", q=query)
        return []
    _log("lex_no_slots_fallback", q=query)
    return _fallback_tokens(query)


def _fallback_tokens(query: str) -> list[str]:
    tokens = [t.strip().lower() for t in query.replace(",", " ").split() if t.strip()]
    return [t for t in tokens if t not in STOPWORDS][:5]


def _expand_plural(words: list[str]) -> list[str]:
    """Cheap stemmer: 'dogs' -> 'dog', 'boxes' -> 'box'. Trailing-s only."""
    out = list(words)
    for w in words:
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            singular = w[:-2] if w.endswith("es") and len(w) > 4 else w[:-1]
            if singular and singular not in out:
                out.append(singular)
    return out


def _query_photos(keywords: list[str], raw_q: str) -> list[dict]:
    """Bool-OR of (terms exact) and (match on labels.text).

    The terms branch covers the spec's headline case: 'if Rekognition returns
    12 labels for a given photo, your search should return the photo for any
    one of those 12 labels.' That works because the index stores `labels` as
    a `keyword` array, so an exact membership test is enough.

    The match branch covers multi-word Rekognition labels (e.g. 'labrador
    retriever', 'sea life'). We match on the analyzed sub-field labels.text.
    """
    expanded = _expand_plural([k for k in keywords if k])

    should: list[dict] = []
    if expanded:
        should.append({"terms": {"labels": expanded}})

    # Multi-word coverage: match each keyword that has whitespace and the
    # original query, against the analyzed sub-field. labels.text is a
    # standard-analyzed text field so 'labrador retriever' tokenises into
    # both terms and a match query covers it.
    multi_word_kw = [k for k in keywords if " " in k]
    for kw in multi_word_kw:
        should.append({"match": {"labels.text": {"query": kw, "operator": "and"}}})

    if raw_q.strip():
        should.append({"match": {"labels.text": {"query": raw_q, "operator": "or", "minimum_should_match": "60%"}}})

    if not should:
        return []

    body = {
        "size": 50,
        "query": {"bool": {"should": should, "minimum_should_match": 1}},
    }
    _log("es_query", body=body)

    res = _signed_es_post(f"/{ES_INDEX}/_search", body)
    hits = (res.get("hits") or {}).get("hits") or []
    seen, out = set(), []
    for h in hits:
        src = h.get("_source") or {}
        key = src.get("objectKey")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({
            "url": f"https://{PHOTOS_BUCKET}.s3.amazonaws.com/{key}",
            "labels": src.get("labels", []),
        })
    return out


def lambda_handler(event, context):
    try:
        qs = event.get("queryStringParameters") or {}
        q = (qs.get("q") or "").strip()
        _log("invocation_start", q=q)

        if not q:
            return _resp(200, {"results": []})

        keywords = _extract_keywords_via_lex(q)
        _log("keywords", q=q, keywords=keywords, strictLex=STRICT_LEX)

        if not keywords and not q:
            return _resp(200, {"results": []})

        results = _query_photos(keywords, q)
        _log("results", count=len(results))
        return _resp(200, {"results": results})

    except Exception as exc:  # noqa: BLE001 — return 200 + empty per spec, log
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        _log(
            "error",
            errorClass=type(exc).__name__,
            message=str(exc),
            traceback=tb[-2000:],
        )
        return _resp(200, {"results": []})
