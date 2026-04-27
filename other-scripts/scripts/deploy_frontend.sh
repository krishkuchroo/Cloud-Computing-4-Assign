#!/usr/bin/env bash
# Syncs front-end/ to B1.
set -euo pipefail
: "${AWS_PROFILE:=nyu}"
export AWS_PROFILE
REGION="us-east-1"
B1="cc-photos-frontend-746140163942"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

aws s3 sync "${ROOT}/front-end/" "s3://${B1}/" \
  --delete \
  --exclude "config.example.js" \
  --exclude ".DS_Store" \
  --region "$REGION"

echo
echo "Frontend live at:"
echo "  http://${B1}.s3-website-${REGION}.amazonaws.com"
