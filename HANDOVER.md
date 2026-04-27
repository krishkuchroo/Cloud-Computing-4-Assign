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
| OpenSearch domain `photos` | `https://search-photos-dhbzsy6k4xwqmfkozq7j2rjgkq.us-east-1.es.amazonaws.com` | `bash other-scripts/scripts/provision_opensearch.sh` then `bash other-scripts/scripts/create_es_index.sh` (now idempotent: re-running adds `labels.text` sub-field + reindexes). |
| Lex V2 bot `cc-photos-search-bot` | bot ID: `T4DPQ3XVUE`, alias ID: `UJABDDPGRP` | `python3 other-scripts/scripts/create_lex_bot.py`. Live bot definition is exported to `other-scripts/lex/SearchIntent_export.json` (regenerated on every grading session). |
| API Key `cc-photos-key` | key ID: `9ybes6n6ik`. Value retrieved via `aws apigateway get-api-key --api-key 9ybes6n6ik --include-value --query value --output text`. | Created automatically by CFN stack. Attached to usage plan `cc-photos-usage-plan` on stage `prod`. |
| GitHub OAuth connection | `arn:aws:codeconnections:us-east-1:746140163942:connection/fdd78895-3be5-4802-922d-f5d36983fc46` (status `AVAILABLE`) | Created via Console once; can be re-authorized in the same place. |
| Two CodePipelines | `cc-photos-backend-pipeline`, `cc-photos-frontend-pipeline` | `CONNECTION_ARN=… GH_OWNER=… GH_REPO=… bash other-scripts/scripts/setup_pipelines.sh` (idempotent). Source: GitHub via the connection above. |

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
- LF1 currently filters on `Content-Type` starting with `image/jpeg|jpg|png` only — Rekognition's supported set. Other image MIME types (`image/heic`, `image/webp`, `image/gif`) are rejected at index time with `event=skipped_non_image`. Acceptable per the assignment scope (the upload form is restricted to JPEG/PNG anyway).
- The fallback tokenizer in LF2 is gated behind `STRICT_LEX=0` (off by default — spec wants empty array on no Lex slots). Flip the env var to re-enable for debugging.
- After re-deploying CFN with `LambdaCodeBucket` empty, run `bash other-scripts/scripts/deploy_lambdas.sh` to push the real code on top of the placeholder. Otherwise the placeholder Lambda answers all PUT events with a no-op.

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