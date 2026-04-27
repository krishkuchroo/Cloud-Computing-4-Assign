# IAM Role ARNs (live, account 746140163942, region us-east-1)

Snapshot taken 2026-04-27. Re-generate any time with:

```bash
AWS_PROFILE=default aws iam list-roles \
  --query "Roles[?starts_with(RoleName, 'cc-photos')].{Name:RoleName,Arn:Arn,Created:CreateDate}" \
  --output table
```

| Role | ARN | Used by |
|---|---|---|
| `cc-photos-lf1-role` | `arn:aws:iam::746140163942:role/cc-photos-lf1-role` | LF1 (`index-photos`) — S3 GetObject on B2, Rekognition.DetectLabels, ES HTTP, SQS SendMessage to DLQ, CloudWatch Logs |
| `cc-photos-lf2-role` | `arn:aws:iam::746140163942:role/cc-photos-lf2-role` | LF2 (`search-photos`) — Lex RecognizeText, ES HTTP, CloudWatch Logs |
| `cc-photos-apigw-s3-role` | `arn:aws:iam::746140163942:role/cc-photos-apigw-s3-role` | API Gateway → S3 service-proxy for PUT /photos |
| `cc-photos-apigw-cw-role` | `arn:aws:iam::746140163942:role/cc-photos-apigw-cw-role` | API Gateway CloudWatch logging (account-level setting) |
| `cc-photos-lex-runtime-role` | `arn:aws:iam::746140163942:role/cc-photos-lex-runtime-role` | Lex V2 runtime — created by `create_lex_bot.py` |
| `cc-photos-codebuild-role` | `arn:aws:iam::746140163942:role/cc-photos-codebuild-role` | CodeBuild for both pipelines (P1, P2) |
| `cc-photos-pipeline-role` | `arn:aws:iam::746140163942:role/cc-photos-pipeline-role` | CodePipeline service role for P1 + P2 |

## Other resource ARNs

| Resource | ARN / ID |
|---|---|
| Lambda LF1 | `arn:aws:lambda:us-east-1:746140163942:function:index-photos` |
| Lambda LF2 | `arn:aws:lambda:us-east-1:746140163942:function:search-photos` |
| OpenSearch domain `photos` | `arn:aws:es:us-east-1:746140163942:domain/photos` |
| OpenSearch endpoint | `https://search-photos-dhbzsy6k4xwqmfkozq7j2rjgkq.us-east-1.es.amazonaws.com` |
| Lex bot `cc-photos-search-bot` | id `T4DPQ3XVUE`, alias `UJABDDPGRP` (locale `en_US`, version `1`) |
| API Gateway REST API `cc-photos-api` | id `bidkb7umjc`, stage `prod` |
| API Key `cc-photos-key` | id `9ybes6n6ik` |
| CFN Stack | `arn:aws:cloudformation:us-east-1:746140163942:stack/cc-photos-stack/*` |
| SQS DLQ for LF1 | `cc-photos-lf1-dlq` (ARN populated when stack updates) |
| CodeStar / CodeConnections (GitHub) | `arn:aws:codeconnections:us-east-1:746140163942:connection/fdd78895-3be5-4802-922d-f5d36983fc46` (status `AVAILABLE`) |

## Frontend / API URLs

- Frontend (B1): `http://cc-photos-frontend-746140163942.s3-website-us-east-1.amazonaws.com`
- API invoke (prod): `https://bidkb7umjc.execute-api.us-east-1.amazonaws.com/prod`
