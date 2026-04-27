#!/usr/bin/env bash
# Configures B1 (frontend static hosting) and B2 (photos, CORS + public read).
# Idempotent: safe to re-run.
set -euo pipefail

: "${AWS_PROFILE:=nyu}"
export AWS_PROFILE
REGION="us-east-1"
ACCOUNT="746140163942"
B1="cc-photos-frontend-${ACCOUNT}"
B2="cc-photos-storage-${ACCOUNT}"

echo "[B1] disable block-public-access on ${B1}"
aws s3api put-public-access-block --bucket "$B1" --region "$REGION" \
  --public-access-block-configuration \
  "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"

echo "[B1] public-read bucket policy"
aws s3api put-bucket-policy --bucket "$B1" --region "$REGION" --policy "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [{
    \"Sid\": \"PublicReadGetObject\",
    \"Effect\": \"Allow\",
    \"Principal\": \"*\",
    \"Action\": \"s3:GetObject\",
    \"Resource\": \"arn:aws:s3:::${B1}/*\"
  }]
}"

echo "[B1] static website hosting"
aws s3 website "s3://${B1}/" --index-document index.html --error-document index.html

echo "[B2] disable block-public-access on ${B2}"
aws s3api put-public-access-block --bucket "$B2" --region "$REGION" \
  --public-access-block-configuration \
  "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"

echo "[B2] public-read bucket policy"
aws s3api put-bucket-policy --bucket "$B2" --region "$REGION" --policy "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [{
    \"Sid\": \"PublicReadGetObject\",
    \"Effect\": \"Allow\",
    \"Principal\": \"*\",
    \"Action\": \"s3:GetObject\",
    \"Resource\": \"arn:aws:s3:::${B2}/*\"
  }]
}"

echo "[B2] CORS for frontend display + APIGW PUT"
aws s3api put-bucket-cors --bucket "$B2" --region "$REGION" --cors-configuration '{
  "CORSRules": [{
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["GET", "PUT", "POST", "HEAD"],
    "AllowedOrigins": ["*"],
    "ExposeHeaders": ["ETag", "x-amz-meta-customlabels"],
    "MaxAgeSeconds": 3000
  }]
}'

echo
echo "Done. B1 website endpoint:"
echo "  http://${B1}.s3-website-${REGION}.amazonaws.com"
echo "B2 photos bucket: ${B2}"
