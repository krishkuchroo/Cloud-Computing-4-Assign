# cc-photos — Photo Album with Natural-Language Search

NYU Cloud Computing Spring 2026, Assignment 3.

A photo album where users upload images (with optional custom labels) and search them using natural English. Rekognition auto-tags each upload, Lex parses search queries into keywords, and OpenSearch returns matching photos.

- Test for codepipeline

## Architecture

```
Frontend (S3 B1) → API Gateway → ┬→ S3 PutObject (B2) → S3 PUT event → LF1 (index-photos) → Rekognition + headObject → OpenSearch
                                  └→ LF2 (search-photos) → Lex (RecognizeText) → OpenSearch query → results
```

Diagram: see `docs/ARCHITECTURE.md` and the annex of the assignment PDF.

## Repo layout
See `CLAUDE.md` for the full file map.

## Prerequisites
- AWS account, region `us-east-1`
- AWS CLI v2 configured (`aws configure`)
- Python 3.12, Node.js 20+ (only for SDK generation)
- IAM permissions: admin, or scoped to S3, Lambda, IAM, OpenSearch, Lex, APIGW, CloudFormation, CodePipeline, CodeBuild

## Deploy from scratch (the actual sequence that worked)

```bash
export AWS_PROFILE=nyu

# 1. Provision OpenSearch (takes ~15 min). Run in background; continue.
bash other-scripts/scripts/provision_opensearch.sh

# 2. Deploy CFN stack (creates B1, B2, both Lambdas, APIGW + key).
aws cloudformation deploy \
  --template-file other-scripts/cfn/template.yaml \
  --stack-name cc-photos-stack \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

# 3. Build and deploy real Lambda code (replaces CFN placeholders).
bash other-scripts/scripts/build_lambdas.sh
bash other-scripts/scripts/deploy_lambdas.sh

# 4. Wait for OpenSearch to be Active, then create the index.
aws opensearch describe-domain --domain-name photos \
  --query 'DomainStatus.Endpoint' --output text  # poll until non-null
export ES_ENDPOINT="https://$(aws opensearch describe-domain --domain-name photos --query 'DomainStatus.Endpoint' --output text)"
bash other-scripts/scripts/create_es_index.sh

# 5. Create the Lex bot. Prints LEX_BOT_ID + LEX_BOT_ALIAS_ID at the end.
python3 -m venv .venv && source .venv/bin/activate && pip install boto3
python other-scripts/scripts/create_lex_bot.py
export LEX_BOT_ID=<from output>
export LEX_BOT_ALIAS_ID=<from output>

# 6. Inject env vars into the deployed Lambdas.
bash other-scripts/scripts/configure_lambda_envs.sh

# 7. Generate the API Gateway JavaScript SDK.
API_ID=$(aws cloudformation describe-stacks --stack-name cc-photos-stack \
  --query "Stacks[0].Outputs[?OutputKey=='ApiInvokeUrl'].OutputValue" --output text \
  | sed -E 's|https://([a-z0-9]+).*|\1|')
aws apigateway get-sdk --rest-api-id "$API_ID" --stage-name prod \
  --sdk-type javascript /tmp/sdk.zip
unzip -o /tmp/sdk.zip -d front-end/sdk/

# 8. Populate front-end/config.js with API URL + key (see config.example.js).
cp front-end/config.example.js front-end/config.js  # then edit
# api key value:
aws apigateway get-api-key --api-key $(aws cloudformation describe-stacks \
  --stack-name cc-photos-stack \
  --query "Stacks[0].Outputs[?OutputKey=='ApiKeyId'].OutputValue" --output text) \
  --include-value --query value --output text

# 9. Push frontend to S3.
bash other-scripts/scripts/deploy_frontend.sh

# 10. CodePipelines (optional, requires GitHub repos + CodeStar connection).
#     See other-scripts/scripts/setup_pipelines.sh header for env vars.
```

## Teardown
```bash
AWS_PROFILE=nyu bash other-scripts/scripts/teardown.sh
```

This empties + deletes both buckets, the CFN stack, the OpenSearch domain, the Lex bot, and the Lex IAM role.

## Cost (us-east-1, week-long dev)
- OpenSearch t3.small.search single-node: ~$25/mo (free tier eligible 750 hr/mo for 12 months)
- Everything else: <$2/mo at test volume
- Tear down OpenSearch between long idle periods to drop to ~$0

## Status
See task list (in conversation) and `docs/ACCEPTANCE.md` for what's done vs pending.

## Handover
For Sachin: see `HANDOVER.md`.
