"""
LF1 — index-photos
Triggered by S3 PUT events on bucket B2 (cc-photos-storage-746140163942).
For each uploaded photo:
  1. Call Rekognition DetectLabels
  2. headObject to read x-amz-meta-customLabels
  3. Merge labels (Rekognition + custom), lowercase + dedupe
  4. PUT document into OpenSearch index "photos" (id = object key)
"""

import json
import os
import urllib.parse
from datetime import datetime, timezone

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import Session as BotoSession
from urllib3 import PoolManager

REGION = os.environ.get("AWS_REGION", "us-east-1")
ES_ENDPOINT = os.environ["ES_ENDPOINT"].rstrip("/")  # e.g. https://search-photos-xxx.us-east-1.es.amazonaws.com
ES_INDEX = os.environ.get("ES_INDEX", "photos")
MAX_LABELS = int(os.environ.get("MAX_LABELS", "20"))
MIN_CONFIDENCE = float(os.environ.get("MIN_CONFIDENCE", "70"))

s3 = boto3.client("s3", region_name=REGION)
rekognition = boto3.client("rekognition", region_name=REGION)
http = PoolManager()
_credentials = BotoSession().get_credentials()


def _signed_es_put(path: str, body: dict) -> dict:
    """SigV4-signed PUT to OpenSearch."""
    url = f"{ES_ENDPOINT}{path}"
    payload = json.dumps(body).encode("utf-8")
    req = AWSRequest(method="PUT", url=url, data=payload,
                     headers={"Content-Type": "application/json"})
    SigV4Auth(_credentials, "es", REGION).add_auth(req)
    resp = http.request("PUT", url, body=payload, headers=dict(req.headers))
    if resp.status >= 300:
        raise RuntimeError(f"OpenSearch PUT failed {resp.status}: {resp.data.decode('utf-8', 'ignore')}")
    return json.loads(resp.data.decode("utf-8"))


def _detect_labels(bucket: str, key: str) -> list[str]:
    resp = rekognition.detect_labels(
        Image={"S3Object": {"Bucket": bucket, "Name": key}},
        MaxLabels=MAX_LABELS,
        MinConfidence=MIN_CONFIDENCE,
    )
    return [lbl["Name"] for lbl in resp.get("Labels", [])]


def _custom_labels(bucket: str, key: str) -> list[str]:
    """Read x-amz-meta-customLabels from S3 headObject. Comma-separated string -> list."""
    head = s3.head_object(Bucket=bucket, Key=key)
    meta = head.get("Metadata", {}) or {}
    # boto3 lowercases user metadata keys; accept either form
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


def lambda_handler(event, context):
    indexed = []
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        rek_labels = _detect_labels(bucket, key)
        cust_labels = _custom_labels(bucket, key)
        labels = _merge(rek_labels, cust_labels)

        doc = {
            "objectKey": key,
            "bucket": bucket,
            "createdTimestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "labels": labels,
        }

        # Document ID = URL-encoded key so re-uploads overwrite (idempotent)
        doc_id = urllib.parse.quote(key, safe="")
        _signed_es_put(f"/{ES_INDEX}/_doc/{doc_id}", doc)

        indexed.append({"key": key, "labelCount": len(labels)})
        print(json.dumps({"event": "indexed", "key": key, "labels": labels}))

    return {"statusCode": 200, "body": json.dumps({"indexed": indexed})}
