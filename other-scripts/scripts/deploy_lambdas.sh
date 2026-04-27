#!/usr/bin/env bash
# Updates LF1 + LF2 function code from dist/*.zip.
# Run after build_lambdas.sh and after the CFN stack creates the function shells.
set -euo pipefail

: "${AWS_PROFILE:=nyu}"
export AWS_PROFILE
REGION="us-east-1"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

push() {
  local fn="$1" zip="$2"
  echo "[deploy] ${fn}"
  aws lambda update-function-code \
    --region "$REGION" \
    --function-name "$fn" \
    --zip-file "fileb://${zip}" \
    --output table --query '{Function:FunctionName,Runtime:Runtime,Last:LastModified,Size:CodeSize}'
}

push index-photos "${ROOT}/dist/index_photos.zip"
push search-photos "${ROOT}/dist/search_photos.zip"
echo "[deploy] done"
