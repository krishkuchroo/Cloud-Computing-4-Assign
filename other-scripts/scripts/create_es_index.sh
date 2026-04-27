#!/usr/bin/env bash
# Idempotent OpenSearch index management for the "photos" index.
#
# Behaviour:
#   - If the index does not exist: PUT it with the locked mapping
#     (other-scripts/es/index_mapping.json).
#   - If the index already exists: PUT _mapping to merge any additive changes
#     (e.g. add the labels.text sub-field) and then POST _update_by_query so
#     existing documents are reindexed through the new analyzer.
#
# Requires:
#   AWS_PROFILE (default: nyu)
#   ES_ENDPOINT  e.g. https://search-photos-xxx.us-east-1.es.amazonaws.com

set -euo pipefail

: "${AWS_PROFILE:=nyu}"
: "${ES_ENDPOINT:?ES_ENDPOINT not set. Export it: export ES_ENDPOINT=https://...}"
export AWS_PROFILE
REGION="us-east-1"
INDEX="photos"
MAPPING_FILE="$(dirname "$0")/../es/index_mapping.json"

python3 - "$ES_ENDPOINT" "$REGION" "$INDEX" "$MAPPING_FILE" <<'PY'
import json, sys, boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

endpoint, region, index, mapping_file = sys.argv[1:5]
endpoint = endpoint.rstrip("/")
with open(mapping_file) as f:
    full = json.load(f)

def call(method, path, body=None):
    url = f"{endpoint}{path}"
    data = json.dumps(body).encode() if body is not None else None
    creds = boto3.Session().get_credentials()
    headers = {"Content-Type":"application/json"} if body is not None else {}
    req = AWSRequest(method=method, url=url, data=data, headers=headers)
    SigV4Auth(creds, "es", region).add_auth(req)
    r = Request(url, data=data, method=method, headers=dict(req.headers))
    try:
        with urlopen(r) as resp:
            return resp.status, resp.read().decode()
    except HTTPError as e:
        return e.code, e.read().decode()

# Does the index exist?
status, _ = call("HEAD", f"/{index}")
if status == 404:
    print(f"[create] index {index} not found, creating with full mapping")
    s,b = call("PUT", f"/{index}", full)
    print(s, b)
elif status == 200:
    print(f"[update] index {index} exists, merging mapping additively")
    # Pull just the mappings.properties subtree for an additive update
    properties_only = {"properties": full["mappings"]["properties"]}
    s,b = call("PUT", f"/{index}/_mapping", properties_only)
    print(s, b)
    print("[reindex] forcing _update_by_query so new sub-fields populate for existing docs")
    s,b = call("POST", f"/{index}/_update_by_query?conflicts=proceed&refresh=true",
               {"query":{"match_all":{}}})
    print(s, b[:500])
else:
    print(f"[error] unexpected HEAD status: {status}")
    sys.exit(1)

# Verify
print("[verify]")
s,b = call("GET", f"/{index}/_mapping")
print(s, b)
PY
