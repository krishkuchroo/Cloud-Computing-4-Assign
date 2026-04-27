#!/usr/bin/env bash
# Tears down everything. Run this when you're done with the assignment.
# Note: must empty the S3 buckets before deleting the CFN stack.
set -euo pipefail

: "${AWS_PROFILE:=nyu}"
export AWS_PROFILE
REGION="us-east-1"
ACCOUNT="746140163942"

echo "[s3] empty B1 + B2 (so CFN can delete them)"
aws s3 rm "s3://cc-photos-frontend-${ACCOUNT}/" --recursive --region "$REGION" || true
aws s3 rm "s3://cc-photos-storage-${ACCOUNT}/"  --recursive --region "$REGION" || true

echo "[cfn] delete stack"
aws cloudformation delete-stack --stack-name cc-photos-stack --region "$REGION"
aws cloudformation wait stack-delete-complete --stack-name cc-photos-stack --region "$REGION" || true

echo "[opensearch] delete domain"
aws opensearch delete-domain --domain-name photos --region "$REGION" || true

echo "[lex] delete bot (use force to skip alias deletion)"
BOT_ID="${LEX_BOT_ID:-T4DPQ3XVUE}"
aws lexv2-models delete-bot --bot-id "$BOT_ID" --skip-resource-in-use-check --region "$REGION" || true

echo "[iam] delete Lex runtime role"
aws iam detach-role-policy --role-name cc-photos-lex-runtime-role --policy-arn arn:aws:iam::aws:policy/AmazonLexFullAccess 2>/dev/null || true
aws iam delete-role --role-name cc-photos-lex-runtime-role 2>/dev/null || true

echo
echo "Done. Verify residual resources:"
echo "  aws s3 ls --profile nyu | grep cc-photos"
echo "  aws lambda list-functions --profile nyu --region us-east-1 --query 'Functions[?contains(FunctionName,\`cc-photos\`)||FunctionName==\`index-photos\`||FunctionName==\`search-photos\`].FunctionName'"
echo "  aws opensearch list-domain-names --profile nyu --region us-east-1"
