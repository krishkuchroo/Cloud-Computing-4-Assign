#!/usr/bin/env bash
# Provisions both CodePipelines (P1 backend, P2 frontend) — single GitHub repo,
# two buildspecs.
#
# Prereqs (one-time, manual):
#   1. Push this repo to GitHub (single repo with all 3 folders).
#   2. AWS console -> Developer Tools -> Settings -> Connections ->
#        Create connection -> GitHub. Authorize. Copy the Connection ARN.
#   3. Export env vars:
#        export CONNECTION_ARN=arn:aws:codeconnections:us-east-1:746140163942:connection/...
#        export GH_OWNER=krishkuchroo
#        export GH_REPO=Cloud-Computing-4-Assign
#        export GH_BRANCH=main
#
# Then:  AWS_PROFILE=nyu bash other-scripts/scripts/setup_pipelines.sh
set -euo pipefail

: "${AWS_PROFILE:=nyu}"
: "${CONNECTION_ARN:?required}"
: "${GH_OWNER:?required}"
: "${GH_REPO:?required}"
: "${GH_BRANCH:=main}"
export AWS_PROFILE
REGION="us-east-1"
ACCOUNT="746140163942"

ARTIFACT_BUCKET="cc-photos-pipeline-artifacts-${ACCOUNT}"
PIPE_ROLE="cc-photos-pipeline-role"
BUILD_ROLE="cc-photos-codebuild-role"

# 1. Artifact bucket (versioned, server-side encrypted)
echo "[s3] artifact bucket"
aws s3api create-bucket --bucket "$ARTIFACT_BUCKET" --region "$REGION" 2>/dev/null || true
aws s3api put-bucket-versioning --bucket "$ARTIFACT_BUCKET" \
  --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket "$ARTIFACT_BUCKET" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

# 2. CodeBuild service role (also reads CFN outputs + APIGW key for buildspec-frontend)
echo "[iam] codebuild role"
cat >/tmp/cb-trust.json <<'EOF'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"codebuild.amazonaws.com"},"Action":"sts:AssumeRole"}]}
EOF
aws iam create-role --role-name "$BUILD_ROLE" --assume-role-policy-document file:///tmp/cb-trust.json 2>/dev/null || true
aws iam put-role-policy --role-name "$BUILD_ROLE" --policy-name codebuild-inline --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [
    {\"Effect\":\"Allow\",\"Action\":[\"logs:CreateLogGroup\",\"logs:CreateLogStream\",\"logs:PutLogEvents\"],\"Resource\":\"*\"},
    {\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\",\"s3:PutObject\",\"s3:DeleteObject\",\"s3:ListBucket\"],\"Resource\":[\"arn:aws:s3:::${ARTIFACT_BUCKET}\",\"arn:aws:s3:::${ARTIFACT_BUCKET}/*\",\"arn:aws:s3:::cc-photos-frontend-${ACCOUNT}\",\"arn:aws:s3:::cc-photos-frontend-${ACCOUNT}/*\"]},
    {\"Effect\":\"Allow\",\"Action\":[\"lambda:UpdateFunctionCode\",\"lambda:GetFunction\"],\"Resource\":[\"arn:aws:lambda:${REGION}:${ACCOUNT}:function:index-photos\",\"arn:aws:lambda:${REGION}:${ACCOUNT}:function:search-photos\"]},
    {\"Effect\":\"Allow\",\"Action\":[\"cloudformation:DescribeStacks\"],\"Resource\":\"arn:aws:cloudformation:${REGION}:${ACCOUNT}:stack/cc-photos-stack/*\"},
    {\"Effect\":\"Allow\",\"Action\":[\"apigateway:GET\"],\"Resource\":\"arn:aws:apigateway:${REGION}::/apikeys/*\"}
  ]
}"

# 3. CodePipeline service role
echo "[iam] codepipeline role"
cat >/tmp/cp-trust.json <<'EOF'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"codepipeline.amazonaws.com"},"Action":"sts:AssumeRole"}]}
EOF
aws iam create-role --role-name "$PIPE_ROLE" --assume-role-policy-document file:///tmp/cp-trust.json 2>/dev/null || true
aws iam put-role-policy --role-name "$PIPE_ROLE" --policy-name codepipeline-inline --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [
    {\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\",\"s3:PutObject\",\"s3:GetBucketVersioning\"],\"Resource\":[\"arn:aws:s3:::${ARTIFACT_BUCKET}\",\"arn:aws:s3:::${ARTIFACT_BUCKET}/*\"]},
    {\"Effect\":\"Allow\",\"Action\":[\"codebuild:StartBuild\",\"codebuild:BatchGetBuilds\"],\"Resource\":\"*\"},
    {\"Effect\":\"Allow\",\"Action\":[\"codestar-connections:UseConnection\",\"codeconnections:UseConnection\"],\"Resource\":\"${CONNECTION_ARN}\"}
  ]
}"

sleep 5  # IAM propagation

# 4. CodeBuild projects (one per pipeline; both point at same repo, different buildspec)
echo "[codebuild] projects"
for pair in "cc-photos-backend-build:other-scripts/pipelines/buildspec-backend.yml" "cc-photos-frontend-build:other-scripts/pipelines/buildspec-frontend.yml"; do
  name="${pair%%:*}"; spec="${pair##*:}"
  aws codebuild create-project --name "$name" \
    --service-role "arn:aws:iam::${ACCOUNT}:role/${BUILD_ROLE}" \
    --source "type=CODEPIPELINE,buildspec=${spec}" \
    --artifacts "type=CODEPIPELINE" \
    --environment "type=LINUX_CONTAINER,image=aws/codebuild/standard:7.0,computeType=BUILD_GENERAL1_SMALL" \
    --region "$REGION" 2>/dev/null || \
  aws codebuild update-project --name "$name" \
    --service-role "arn:aws:iam::${ACCOUNT}:role/${BUILD_ROLE}" \
    --source "type=CODEPIPELINE,buildspec=${spec}" \
    --artifacts "type=CODEPIPELINE" \
    --environment "type=LINUX_CONTAINER,image=aws/codebuild/standard:7.0,computeType=BUILD_GENERAL1_SMALL" \
    --region "$REGION" >/dev/null
done

# 5. Pipelines (both point at same GitHub repo + branch)
mk_pipeline() {
  local pname="$1" build="$2"
  cat >/tmp/pipeline-${pname}.json <<EOF
{
  "pipeline": {
    "name": "${pname}",
    "roleArn": "arn:aws:iam::${ACCOUNT}:role/${PIPE_ROLE}",
    "artifactStore": {"type": "S3", "location": "${ARTIFACT_BUCKET}"},
    "stages": [
      {
        "name": "Source",
        "actions": [{
          "name": "Source",
          "actionTypeId": {"category": "Source", "owner": "AWS", "provider": "CodeStarSourceConnection", "version": "1"},
          "configuration": {
            "ConnectionArn": "${CONNECTION_ARN}",
            "FullRepositoryId": "${GH_OWNER}/${GH_REPO}",
            "BranchName": "${GH_BRANCH}",
            "OutputArtifactFormat": "CODE_ZIP"
          },
          "outputArtifacts": [{"name": "src"}]
        }]
      },
      {
        "name": "Build",
        "actions": [{
          "name": "Build",
          "actionTypeId": {"category": "Build", "owner": "AWS", "provider": "CodeBuild", "version": "1"},
          "configuration": {"ProjectName": "${build}"},
          "inputArtifacts": [{"name": "src"}],
          "outputArtifacts": [{"name": "out"}]
        }]
      }
    ],
    "version": 1
  }
}
EOF
  echo "[pipeline] ${pname}"
  aws codepipeline create-pipeline --cli-input-json "file:///tmp/pipeline-${pname}.json" --region "$REGION" 2>/dev/null || \
  aws codepipeline update-pipeline --cli-input-json "file:///tmp/pipeline-${pname}.json" --region "$REGION" >/dev/null
}

mk_pipeline cc-photos-backend-pipeline  cc-photos-backend-build
mk_pipeline cc-photos-frontend-pipeline cc-photos-frontend-build

echo
echo "Done. Pipelines visible at:"
echo "  https://${REGION}.console.aws.amazon.com/codesuite/codepipeline/pipelines"
