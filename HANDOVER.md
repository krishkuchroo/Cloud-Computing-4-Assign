# HANDOVER.md — for Sachin

Personal context, account-specific values, and known issues. Not for public commits.

## Authors
- Krish Kuchroo (kk5846@nyu.edu) — primary
- Sachin (incoming co-owner)

## AWS account access
- Account ID: `746140163942`
- Region: `us-east-1`
- Console URL: `https://746140163942.signin.aws.amazon.com/console`
- Shared IAM user: `krish-sachin` (used by both of us via the `nyu` AWS CLI profile)
- AWS CLI: `export AWS_PROFILE=nyu` before running any script in this repo
- MFA: configure if not already.

## Pre-existing resources in this account (NOT ours, leave alone)
From prior assignments — confirmed via inventory on 2026-04-26:
- S3: `cc-hw1-chatbot-frontend` (HW1)
- Lambdas: `dining-concierge-LF0`, `dining-concierge-LF1`, `dining-concierge-LF2`, `vf-scraper-cron` (HW2)
- No OpenSearch domains, no CFN stacks at start.

Our resources all use the `cc-photos-` prefix to keep them grouped and avoid collision.

## Manually-created resources (NOT in CloudFormation)

These are out of T1 scope per the assignment. If the stack is deleted, these survive.

| Resource | Identifier | How it was made |
|---|---|---|
| OpenSearch domain `photos` | endpoint: `<fill in after provision>` | Console → OpenSearch → Create domain. t3.small.search, 1 node, single AZ, 10GB gp3. Fine-grained access OFF, IAM-based access policy attached. |
| Lex V2 bot `cc-photos-search-bot` | bot ID: `<fill in>`, alias ID: `<fill in>` | Console → Lex V2 → Import → upload `other-scripts/lex/SearchIntent_export.json` |
| API Key `cc-photos-key` | key ID: `<fill in>`, value: `<fill in>` | Console → APIGW → API Keys → Create. Attach to usage plan `cc-photos-usage-plan` linked to stage `prod`. |
| GitHub OAuth connection | CodeStar connection ARN: `<fill in>` | Console → Developer Tools → Connections → Create connection → GitHub. Authorize once. |
| Two CodePipelines | `cc-photos-backend-pipeline`, `cc-photos-frontend-pipeline` | Created via console using buildspecs in `pipelines/`. Source: GitHub via CodeStar connection above. |

## Stack outputs (live as of 2026-04-26)
- Frontend URL: `http://cc-photos-frontend-746140163942.s3-website-us-east-1.amazonaws.com`
- API invoke URL: `https://bidkb7umjc.execute-api.us-east-1.amazonaws.com/prod`
- Photos bucket: `cc-photos-storage-746140163942`
- Frontend bucket: `cc-photos-frontend-746140163942`
- API Key ID: `9ybes6n6ik`
- API Key value: stored locally only (run `aws apigateway get-api-key --api-key 9ybes6n6ik --include-value --query value --output text --profile nyu` to retrieve)
- OpenSearch endpoint: `https://search-photos-dhbzsy6k4xwqmfkozq7j2rjgkq.us-east-1.es.amazonaws.com`
- Lex bot ID: `T4DPQ3XVUE`, alias ID: `UJABDDPGRP`, locale: `en_US`

## Where things live in the console
- Lambdas: us-east-1 → Lambda → `index-photos` and `search-photos`
- ES domain: us-east-1 → OpenSearch Service → `photos`
- API: us-east-1 → API Gateway → `cc-photos-api` → stage `prod`
- Lex: us-east-1 → Lex V2 → Bots → `cc-photos-search-bot`
- Pipelines: us-east-1 → CodePipeline

## Local dev
1. Clone the two GitHub repos (URLs in `<fill in>` once created).
2. `aws configure --profile cc-photos` then `export AWS_PROFILE=cc-photos`.
3. To test LF1 locally: `cd lambda-functions/index_photos && python -m pytest tests/` (after we add tests).
4. To redeploy a Lambda quickly without waiting for the pipeline: `bash scripts/quick_deploy_lambda.sh index-photos`

## Known issues / WIP
- (populated as we hit them)

## Demo script (for grading session)
1. Open frontend URL.
2. Upload a photo with custom labels `Sam, Sally`.
3. Wait ~5 sec for indexing.
4. Search "show me Sam" → photo appears.
5. Search a Rekognition-detected label (e.g. "person") → photo appears.
6. Search "show me cats and dogs" with relevant photos uploaded → both return.
7. Push a trivial commit to backend repo → CodePipeline runs → Lambda updated.
8. Show CFN stack in console → resources created.

## Cost watchdog
- Set a CloudWatch billing alarm at $20/mo as a safety net.
- OpenSearch is the only meaningful cost. If we won't touch the project for 3+ days, delete the domain and re-create on return.