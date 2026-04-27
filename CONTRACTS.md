# CONTRACTS.md

Single source of truth for cross-track interfaces. Locked at kickoff.
**If you need to change something here, stop and announce it before editing — every track depends on this file.**

---

## 1. AWS Account & Region

- **Region:** `us-east-1`
- **Account:** `746140163942` (NYU shared account, IAM user `krish-sachin`)
- **Profile:** `nyu` — set `export AWS_PROFILE=nyu` in your shell before running any script

---

## 2. Resource Naming Convention

All resources prefixed with `cc-photos-` to keep things groupable in the console.

| Resource | Name | Symbol in PDF |
|---|---|---|
| Frontend S3 bucket | `cc-photos-frontend-746140163942` | B1 |
| Photos S3 bucket | `cc-photos-storage-746140163942` | B2 |
| Index Lambda | `index-photos` | LF1 |
| Search Lambda | `search-photos` | LF2 |
| OpenSearch domain | `photos` | (ES) |
| OpenSearch index | `photos` | — |
| Lex bot | `cc-photos-search-bot` | — |
| Lex intent | `SearchIntent` | — |
| API Gateway REST API | `cc-photos-api` | — |
| API Stage | `prod` | — |
| API Key | `cc-photos-key` | — |
| CFN Stack | `cc-photos-stack` | T1 |
| Lambda CodePipeline | `cc-photos-backend-pipeline` | P1 |
| Frontend CodePipeline | `cc-photos-frontend-pipeline` | P2 |

`<account-id>` suffix on S3 buckets because S3 names are globally unique.

---

## 3. IAM Roles (least privilege)

| Role | Trust | Permissions |
|---|---|---|
| `cc-photos-lf1-role` | lambda.amazonaws.com | s3:GetObject + s3:GetObjectTagging on B2; rekognition:DetectLabels (*); es:ESHttpPost + es:ESHttpPut on `photos` index; CloudWatch Logs basic |
| `cc-photos-lf2-role` | lambda.amazonaws.com | lex:RecognizeText on bot; es:ESHttpGet + es:ESHttpPost on `photos` index; CloudWatch Logs basic |
| `cc-photos-apigw-s3-role` | apigateway.amazonaws.com | s3:PutObject + s3:PutObjectAcl on B2 |
| `cc-photos-pipeline-role` | codepipeline.amazonaws.com | Standard pipeline + CodeBuild + Lambda update + S3 sync |

ARNs to be filled in after first deploy → published to `docs/IAM_ARNS.md` by the Infra agent.

---

## 4. ElasticSearch / OpenSearch

**Domain config (cost-optimized):**
- Engine: OpenSearch 2.x (latest available)
- Instance: `t3.small.search`, **1 node**, single AZ
- Storage: 10 GB EBS gp3
- Access: fine-grained access control DISABLED, use IAM-based access policy
- HTTPS only, TLS 1.2+

**Index name:** `photos`

**Index mapping (locked):**
```json
{
  "mappings": {
    "properties": {
      "objectKey":        { "type": "keyword" },
      "bucket":           { "type": "keyword" },
      "createdTimestamp": { "type": "date" },
      "labels":           { "type": "keyword" }
    }
  }
}
```

`labels` is `keyword` (not `text`) so exact-match `terms` queries work for the acceptance criterion: any one of N Rekognition labels must independently retrieve the photo.

**Document schema (locked, per PDF page 2):**
```json
{
  "objectKey": "my-photo.jpg",
  "bucket": "cc-photos-storage-746140163942",
  "createdTimestamp": "2026-04-26T12:40:02",
  "labels": ["person", "dog", "ball", "park"]
}
```

Document ID = S3 object key. This makes re-uploads idempotent (overwrite, don't duplicate).

**Search query DSL (used by LF2):**
```json
{
  "query": {
    "terms": {
      "labels": ["<k1>", "<k2>", "..."]
    }
  },
  "size": 50
}
```

---

## 5. API Contract (API Gateway REST API)

Two methods on stage `prod`. Both require `x-api-key` header.

### PUT /photos/{bucket}/{key}

**Integration:** AWS Service proxy → S3 PutObject. **Not a Lambda.**
**Path params:** `bucket` (always B2), `key` (filename)
**Headers in:**
- `x-api-key` (required, API Gateway enforces)
- `Content-Type` (passed through to S3)
- `x-amz-meta-customLabels` (optional, comma-separated, e.g. `Sam, Sally`)
**Body:** binary image (configure binary media types: `image/jpeg`, `image/png`, `*/*`)
**Response:** 200 on success, S3 response body

### GET /search?q={query}

**Integration:** Lambda proxy → LF2
**Query params:** `q` (URL-encoded search string)
**Headers in:** `x-api-key`
**Response (per assignment swagger):**
```json
{
  "results": [
    {
      "url": "https://cc-photos-storage-746140163942.s3.amazonaws.com/<key>",
      "labels": ["person", "dog"]
    }
  ]
}
```

Empty results: `{ "results": [] }` (not 404).

### CORS

Both methods need OPTIONS preflight enabled.
- `Access-Control-Allow-Origin: *` (tighten to frontend bucket URL post-launch if time permits)
- `Access-Control-Allow-Headers: Content-Type, x-api-key, x-amz-meta-customLabels`
- `Access-Control-Allow-Methods: GET, PUT, OPTIONS`

---

## 6. Lex V2 Bot

- **Bot:** `cc-photos-search-bot`, en_US, Voice & Text
- **Intent:** `SearchIntent`
- **Slot type:** `AMAZON.AlphaNumeric` or custom — use built-in for first pass
- **Slots:** `keyword1` (required), `keyword2` (optional)
- **Sample utterances (minimum set):**
  - `{keyword1}`
  - `show me {keyword1}`
  - `find {keyword1}`
  - `photos of {keyword1}`
  - `show me photos with {keyword1} and {keyword2}`
  - `find {keyword1} and {keyword2}`
  - `{keyword1} and {keyword2}`
- **Fulfillment:** None (LF2 just reads slot values from RecognizeText response)
- **Build before LF2 testing.**

---

## 7. Frontend Contract

- **Framework:** Vanilla HTML/JS (no build step → simpler CodePipeline)
- **SDK:** API Gateway-generated JS SDK in `front-end/sdk/`
- **API key:** injected at runtime from a `config.js` file (gitignored, populated post-deploy)
- **Pages:**
  - Search bar + results grid (thumbnails)
  - Upload form: file input + custom labels text field (comma-separated)
- **Upload flow:** read file as binary, PUT via SDK with `x-amz-meta-customLabels` header

---

## 8. CloudFormation Scope (locked)

T1 includes ONLY:
- Both S3 buckets (B1, B2) with website config on B1
- Both Lambda functions (LF1, LF2) — code from inline ZIP or GitHub source
- API Gateway REST API + both methods + deployment + stage
- IAM roles for the above

T1 does NOT include:
- OpenSearch domain
- Lex bot
- CodePipelines
- API Key (created manually, ARN passed as parameter if needed)

Stack outputs:
- Frontend website URL
- API invoke URL
- B2 bucket name (for upload form)

---

## 9. Conventions

- Python 3.12 for Lambdas
- `requirements.txt` per Lambda; build via `pip install -r requirements.txt -t .` then zip
- All CloudWatch log groups: 7-day retention
- No secrets in code. API key, ES endpoint, bot ID injected via Lambda env vars or SSM
- Commit messages: `<track>: <verb> <thing>` e.g. `backend: add headObject custom label parsing`
