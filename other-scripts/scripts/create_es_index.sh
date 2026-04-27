#!/usr/bin/env bash
# Creates the "photos" index on the OpenSearch domain with the locked mapping.
# Idempotent in spirit: prints a clear message if the index already exists.
# Requires: ES_ENDPOINT env var (e.g. https://search-photos-xxx.us-east-1.es.amazonaws.com)
#           AWS_PROFILE=nyu (or default credentials with es:ESHttpPut on the index)
set -euo pipefail

: "${AWS_PROFILE:=nyu}"
: "${ES_ENDPOINT:?ES_ENDPOINT not set. Export it: export ES_ENDPOINT=https://...}"
export AWS_PROFILE
REGION="us-east-1"
INDEX="photos"
MAPPING_FILE="$(dirname "$0")/../es/index_mapping.json"

URL="${ES_ENDPOINT%/}/${INDEX}"
echo "Creating index ${INDEX} at ${URL}"

# Use awscurl (preferred) or fall back to python+requests-aws4auth
if command -v awscurl >/dev/null 2>&1; then
  awscurl --service es --region "$REGION" -X PUT "$URL" \
    -H "Content-Type: application/json" \
    --data "@${MAPPING_FILE}" || true
else
  python3 - <<PY
import json, os, sys, boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
url = "${URL}"
with open("${MAPPING_FILE}", "rb") as f:
    body = f.read()
creds = boto3.Session().get_credentials()
req = AWSRequest(method="PUT", url=url, data=body, headers={"Content-Type": "application/json"})
SigV4Auth(creds, "es", "${REGION}").add_auth(req)
r = Request(url, data=body, method="PUT", headers=dict(req.headers))
try:
    with urlopen(r) as resp:
        print(resp.status, resp.read().decode())
except HTTPError as e:
    print(e.code, e.read().decode())
PY
fi
echo
echo "Done."
