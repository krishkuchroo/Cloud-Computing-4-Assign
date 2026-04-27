#!/usr/bin/env bash
# Phase 1 verification, wrapped. Exits 0 if everything is alive, non-zero otherwise.
# Run with AWS_PROFILE=default (or =nyu if you have that profile aliased).
set -uo pipefail

: "${AWS_PROFILE:=default}"
export AWS_PROFILE
REGION="us-east-1"
ACCOUNT="746140163942"

fail=0
ok()   { printf "  [ OK ] %s\n" "$1"; }
bad()  { printf "  [FAIL] %s\n" "$1"; fail=$((fail+1)); }
note() { printf "  [INFO] %s\n" "$1"; }

echo "== AWS identity =="
ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) || true
if [[ "$ID" == "$ACCOUNT" ]]; then ok "Account $ID"; else bad "Account is '$ID', expected $ACCOUNT"; fi

echo "== OpenSearch =="
EP=$(aws opensearch describe-domain --domain-name photos --region "$REGION" \
       --query 'DomainStatus.Endpoint' --output text 2>/dev/null)
PROC=$(aws opensearch describe-domain --domain-name photos --region "$REGION" \
       --query 'DomainStatus.Processing' --output text 2>/dev/null)
[[ "$EP" != None && -n "$EP" ]] && ok "domain endpoint $EP" || bad "no endpoint"
[[ "$PROC" == "False" ]] && ok "Processing=False" || bad "Processing=$PROC (still settling)"

echo "== CFN stack =="
ST=$(aws cloudformation describe-stacks --stack-name cc-photos-stack --region "$REGION" \
       --query 'Stacks[0].StackStatus' --output text 2>/dev/null)
case "$ST" in
  CREATE_COMPLETE|UPDATE_COMPLETE) ok "stack $ST" ;;
  *) bad "stack status $ST" ;;
esac

echo "== Lambdas =="
for fn in index-photos search-photos; do
  ENV=$(aws lambda get-function-configuration --function-name "$fn" --region "$REGION" \
         --query 'Environment.Variables' --output json 2>/dev/null)
  if echo "$ENV" | grep -q ES_ENDPOINT; then ok "$fn env has ES_ENDPOINT"; else bad "$fn missing ES_ENDPOINT"; fi
  if [[ "$fn" == "search-photos" ]]; then
    echo "$ENV" | grep -q LEX_BOT_ID && ok "$fn env has LEX_BOT_ID" || bad "$fn missing LEX_BOT_ID"
  fi
done

echo "== Lex =="
S=$(aws lexv2-models describe-bot-alias --bot-id T4DPQ3XVUE --bot-alias-id UJABDDPGRP \
      --region "$REGION" --query 'botAliasStatus' --output text 2>/dev/null)
[[ "$S" == "Available" ]] && ok "alias prod Available" || bad "alias status $S"

echo "== APIGW =="
LU=$(aws apigateway get-stage --rest-api-id bidkb7umjc --stage-name prod --region "$REGION" \
       --query 'lastUpdatedDate' --output text 2>/dev/null)
[[ -n "$LU" && "$LU" != "None" ]] && ok "stage prod last updated $LU" || bad "stage prod missing"

echo "== Frontend =="
URL="http://cc-photos-frontend-${ACCOUNT}.s3-website-${REGION}.amazonaws.com"
HTTP=$(curl -sI "$URL/index.html" | head -1)
echo "$HTTP" | grep -q "200" && ok "$HTTP" || bad "GET $URL/index.html -> $HTTP"

CFG=$(curl -s "$URL/config.js")
echo "$CFG" | grep -q "apiBaseUrl"   && ok "config.js has apiBaseUrl"  || bad "config.js missing apiBaseUrl"
echo "$CFG" | grep -q "apiKey"       && ok "config.js has apiKey"      || bad "config.js missing apiKey"
echo "$CFG" | grep -q "photosBucket" && ok "config.js has photosBucket"|| bad "config.js missing photosBucket"

echo "== Pipelines =="
P=$(aws codepipeline list-pipelines --region "$REGION" \
      --query "pipelines[?contains(name,'cc-photos')].name" --output text 2>/dev/null)
if [[ -z "$P" ]]; then
  note "no CodePipelines yet (P1, P2 pending)"
else
  for p in $P; do ok "pipeline $p"; done
fi

echo
if (( fail == 0 )); then
  echo "all green."
  exit 0
else
  echo "$fail check(s) failed."
  exit 1
fi
