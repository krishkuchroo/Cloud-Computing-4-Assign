#!/usr/bin/env bash
# Injects env vars (ES_ENDPOINT, LEX_BOT_ID, LEX_BOT_ALIAS_ID) into the deployed Lambdas.
# Required env: ES_ENDPOINT, LEX_BOT_ID, LEX_BOT_ALIAS_ID
set -euo pipefail

: "${AWS_PROFILE:=nyu}"
: "${ES_ENDPOINT:?required}"
: "${LEX_BOT_ID:?required}"
: "${LEX_BOT_ALIAS_ID:?required}"
export AWS_PROFILE
REGION="us-east-1"

echo "[env] index-photos"
aws lambda update-function-configuration \
  --region "$REGION" \
  --function-name index-photos \
  --environment "Variables={ES_ENDPOINT=${ES_ENDPOINT},ES_INDEX=photos,MAX_LABELS=20,MIN_CONFIDENCE=70}" \
  --output table --query 'Environment.Variables'

echo "[env] search-photos"
aws lambda update-function-configuration \
  --region "$REGION" \
  --function-name search-photos \
  --environment "Variables={ES_ENDPOINT=${ES_ENDPOINT},ES_INDEX=photos,LEX_BOT_ID=${LEX_BOT_ID},LEX_BOT_ALIAS_ID=${LEX_BOT_ALIAS_ID},LEX_LOCALE_ID=en_US,PHOTOS_BUCKET=cc-photos-storage-746140163942}" \
  --output table --query 'Environment.Variables'
