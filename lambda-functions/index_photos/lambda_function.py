"""
LF1 — index-photos
Triggered by S3 PUT events on bucket B2 (cc-photos-storage-746140163942).

For each uploaded object:
  1. headObject -> read ContentType, ContentLength, x-amz-meta-customLabels
  2. Skip non-image / zero-byte objects (logged, no DLQ).
  3. Rekognition.detect_labels (S3 reference, no body download).
  4. Merge Rekognition labels + custom labels (lowercase, dedupe, preserve order).
  5. SigV4-signed PUT into OpenSearch index "photos", id = url-encoded object key.
     Re-uploading the same key overwrites the doc (idempotent).

Per-record errors are caught and logged; one bad record never fails its peers.
Transient AWS errors (ThrottlingException, RequestTimeout, 5xx) are re-raised
so the Lambda retry mechanism can replay them; permanent failures are recorded
in the response and the Lambda exits 200 (so S3 doesn't retry indefinitely).

Env vars:
  ES_ENDPOINT        required, e.g. https://search-photos-xxx.us-east-1.es.amazonaws.com
  ES_INDEX           default "photos"
  MAX_LABELS         default "20" (Rekognition.detect_labels MaxLabels)
  MIN_CONFIDENCE     default "50" (Rekognition.detect_labels MinConfidence)
  AWS_REGION         injected by Lambda runtime
"""

import json
import os
import sys
import traceback
import urllib.parse
from datetime import datetime, timezone

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.exceptions import ClientError
from botocore.session import Session as BotoSession
from urllib3 import PoolManager

REGION = os.environ.get("AWS_REGION", "us-east-1")
ES_ENDPOINT = os.environ["ES_ENDPOINT"].rstrip("/")
ES_INDEX = os.environ.get("ES_INDEX", "photos")
MAX_LABELS = int(os.environ.get("MAX_LABELS", "20"))
MIN_CONFIDENCE = float(os.environ.get("MIN_CONFIDENCE", "50"))

# Rekognition supports JPEG and PNG only. Anything else -> skip with a clear log.
SUPPORTED_PREFIXES = ("image/jpeg", "image/jpg", "image/png")

# AWS errors that are worth retrying via Lambda's automatic retry path.
RETRIABLE_CODES = {
    "ThrottlingException",
    "ProvisionedThroughputExceededException",
    "RequestTimeout",
    "RequestTimeoutException",
    "ServiceUnavailable",
    "InternalServerError",
    "InternalFailure",
}

s3 = boto3.client("s3", region_name=REGION)
rekognition = boto3.client("rekognition", region_name=REGION)
http = PoolManager(timeout=10.0, retries=False)
_credentials = BotoSession().get_credentials()


def _log(event: str, **fields) -> None:
    """Single-line JSON log to CloudWatch — easy to query with Logs Insights."""
    payload = {"event": event, **fields}
    try:
        print(json.dumps(payload, default=str))
    except (TypeError, ValueError):
        print(json.dumps({"event": "log_serialize_failed", "raw": str(payload)}))


def _signed_es_put(path: str, body: dict) -> dict:
    """SigV4-signed PUT to OpenSearch."""
    url = f"{ES_ENDPOINT}{path}"
    payload = json.dumps(body).encode("utf-8")
    req = AWSRequest(
        method="PUT", url=url, data=payload,
        headers={"Content-Type": "application/json"},
    )
    SigV4Auth(_credentials, "es", REGION).add_auth(req)
    resp = http.request("PUT", url, body=payload, headers=dict(req.headers))
    if resp.status >= 300:
        raise RuntimeError(
            f"OpenSearch PUT failed status={resp.status} "
            f"body={resp.data.decode('utf-8', 'ignore')[:500]}"
        )
    return json.loads(resp.data.decode("utf-8"))


def _detect_labels(bucket: str, key: str) -> list[str]:
    resp = rekognition.detect_labels(
        Image={"S3Object": {"Bucket": bucket, "Name": key}},
        MaxLabels=MAX_LABELS,
        MinConfidence=MIN_CONFIDENCE,
    )
    return [lbl["Name"] for lbl in resp.get("Labels", [])]


def _head_object(bucket: str, key: str) -> dict:
    """headObject for ContentType, ContentLength, and the custom labels metadata."""
    return s3.head_object(Bucket=bucket, Key=key)


def _custom_labels_from_head(head: dict) -> list[str]:
    """boto3 lowercases user metadata keys; accept both forms for safety."""
    meta = head.get("Metadata", {}) or {}
    raw = meta.get("customlabels") or meta.get("customLabels") or ""
    return [s.strip() for s in raw.split(",") if s.strip()]


def _merge(*lists: list[str]) -> list[str]:
    """Lowercase + dedupe while preserving first-seen order."""
    seen, out = set(), []
    for lst in lists:
        for item in lst:
            k = item.strip().lower()
            if k and k not in seen:
                seen.add(k)
                out.append(k)
    return out


def _is_retriable(exc: Exception) -> bool:
    """True if this error should re-raise so Lambda retries the whole event."""
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        if code in RETRIABLE_CODES:
            return True
        # 5xx HTTP from any AWS service
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if isinstance(status, int) and 500 <= status < 600:
            return True
    return False


def _handle_record(record: dict) -> dict:
    """Process a single S3 event record. Returns a status dict for the response."""
    bucket = record["s3"]["bucket"]["name"]
    raw_key = record["s3"]["object"]["key"]
    key = urllib.parse.unquote_plus(raw_key)
    base = {"bucket": bucket, "key": key}

    # 1. headObject up front — gives us ContentType, ContentLength, and metadata
    #    in one call, so we can decide to skip before paying for Rekognition.
    head = _head_object(bucket, key)
    content_type = (head.get("ContentType") or "").lower()
    content_length = int(head.get("ContentLength") or 0)

    if content_length == 0:
        _log("skipped_empty", **base)
        return {**base, "status": "skipped_empty"}

    if not any(content_type.startswith(p) for p in SUPPORTED_PREFIXES):
        _log("skipped_non_image", contentType=content_type, **base)
        return {**base, "status": "skipped_non_image", "contentType": content_type}

    # 2. Rekognition + custom labels merge.
    rek_labels = _detect_labels(bucket, key)
    cust_labels = _custom_labels_from_head(head)
    labels = _merge(rek_labels, cust_labels)

    doc = {
        "objectKey": key,
        "bucket": bucket,
        "createdTimestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "labels": labels,
    }

    # 3. Index. Document id = URL-encoded key so re-uploads overwrite (idempotent)
    #    and slashes in the key don't become path separators.
    doc_id = urllib.parse.quote(key, safe="")
    _signed_es_put(f"/{ES_INDEX}/_doc/{doc_id}", doc)

    _log(
        "indexed",
        labelCount=len(labels),
        rekCount=len(rek_labels),
        customCount=len(cust_labels),
        contentType=content_type,
        contentLength=content_length,
        **base,
    )
    return {
        **base,
        "status": "indexed",
        "labelCount": len(labels),
        "rekCount": len(rek_labels),
        "customCount": len(cust_labels),
    }


def lambda_handler(event, context):
    records = event.get("Records") or []
    _log("invocation_start", recordCount=len(records))

    results, failed = [], []
    retriable_exc: Exception | None = None

    for record in records:
        try:
            results.append(_handle_record(record))
        except Exception as exc:  # noqa: BLE001 — we want to catch *everything* per-record
            key = "<unknown>"
            try:
                key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
            except Exception:  # pragma: no cover
                pass
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            _log(
                "error",
                key=key,
                errorClass=type(exc).__name__,
                message=str(exc),
                traceback=tb[-2000:],  # keep log lines bounded
                retriable=_is_retriable(exc),
            )
            failed.append({"key": key, "errorClass": type(exc).__name__, "message": str(exc)})
            if _is_retriable(exc) and retriable_exc is None:
                retriable_exc = exc

    summary = {"indexed": results, "failed": failed}
    _log("invocation_end", **{k: len(v) for k, v in summary.items()})

    # If any record failed *retriably*, raise so Lambda retries the whole event.
    # Permanent failures are returned in the body — S3 has already accepted the upload
    # and there's nothing useful to retry.
    if retriable_exc is not None:
        raise retriable_exc

    return {"statusCode": 200, "body": json.dumps(summary)}
