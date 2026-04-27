#!/usr/bin/env bash
# Provisions the OpenSearch domain `photos`.
# Cost: t3.small.search is free-tier eligible 750hr/mo for 12 months on a new account.
# Out-of-tier ~$25/mo. Single node, single AZ, 10GB EBS.
# Takes ~15 minutes to become Active.
set -euo pipefail

: "${AWS_PROFILE:=nyu}"
export AWS_PROFILE
REGION="us-east-1"
ACCOUNT="746140163942"
DOMAIN="photos"

# Allow any IAM principal in our account with explicit permissions.
# (For finer scoping, replace root with specific role ARNs after Lambdas are deployed.)
POLICY_FILE="$(mktemp -t cc-photos-es-policy.XXXXXX.json)"
trap "rm -f '$POLICY_FILE'" EXIT
printf '%s' "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"AWS\":\"arn:aws:iam::${ACCOUNT}:root\"},\"Action\":\"es:*\",\"Resource\":\"arn:aws:es:${REGION}:${ACCOUNT}:domain/${DOMAIN}/*\"}]}" > "$POLICY_FILE"

aws opensearch create-domain \
  --domain-name "$DOMAIN" \
  --region "$REGION" \
  --engine-version "OpenSearch_2.11" \
  --cluster-config "InstanceType=t3.small.search,InstanceCount=1,DedicatedMasterEnabled=false,ZoneAwarenessEnabled=false" \
  --ebs-options "EBSEnabled=true,VolumeType=gp3,VolumeSize=10" \
  --node-to-node-encryption-options "Enabled=true" \
  --encryption-at-rest-options "Enabled=true" \
  --domain-endpoint-options "EnforceHTTPS=true,TLSSecurityPolicy=Policy-Min-TLS-1-2-2019-07" \
  --access-policies "file://${POLICY_FILE}"

echo
echo "Provisioning started. Poll status with:"
echo "  aws opensearch describe-domain --domain-name ${DOMAIN} --region ${REGION} --query 'DomainStatus.Processing'"
echo "When 'Processing' is false, get the endpoint:"
echo "  aws opensearch describe-domain --domain-name ${DOMAIN} --region ${REGION} --query 'DomainStatus.Endpoint' --output text"
