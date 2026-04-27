# CLAUDE.md

Context for Claude sessions on this repo. Read first.

## What this is
NYU Cloud Computing Spring 2026 Assignment 3: photo album with natural-language search.
Stack: S3, Lambda, OpenSearch, Lex V2, Rekognition, API Gateway, CodePipeline, CloudFormation.
Region: `us-east-1`. Account-specific values live in `HANDOVER.md` (gitignored).

## Source of truth
- Spec: `CC_Spring2026_Assignment3 (1).pdf`
- Cross-track interfaces: `CONTRACTS.md` — do not change without announcing
- Submission checklist: `docs/ACCEPTANCE.md`

## Layout
```
lambda-functions/index_photos/   LF1 — S3 PUT trigger, Rekognition + headObject + ES indexing
lambda-functions/search_photos/  LF2 — Lex disambiguation + ES query
front-end/               Vanilla JS app, hosted on B1
front-end/sdk/           API Gateway-generated JS SDK (do not hand-edit)
lex/                    SearchIntent bot export (Lex V2 JSON)
es/                     OpenSearch index mapping
other-scripts/cfn/template.yaml       CloudFormation T1 (Lambdas + APIGW + 2 S3 only)
pipelines/              CodeBuild buildspec files (one per pipeline)
scripts/                provision.sh, teardown.sh — manual steps automated
docs/                   ARCHITECTURE.md, ACCEPTANCE.md, IAM_ARNS.md
```

## Status (2026-04-27 evening)
End-to-end working in AWS, plus all gap-fix work from the 2026-04-27 audit landed: per-record error isolation in LF1, DLQ for LF1, content-type / zero-byte filtering, lower MIN_CONFIDENCE (50), 200-on-error in LF2, multi-word label coverage via `labels.text` sub-field + bool-OR query, generated SDK integrated in front-end, drift-proof Lambda code via CFN parameters, full IAM_ARNS.md, Lex export written, submission script. Outstanding: trigger first run of P1/P2 (pipelines themselves are scripted and ready), final demo screenshots.

## Plan in flight
Plan B (three parallel tracks): Backend, Frontend, Infra. See `CONTRACTS.md` §1–9 for the locked interfaces between them.

## Conventions
- Python 3.12 Lambdas, 256 MB memory
- Resource names prefixed `cc-photos-`
- ES index `photos`, document ID = S3 object key (idempotent re-uploads)
- `labels` field is `keyword` not `text` (exact match needed for grading)
- All CloudWatch log groups: 7-day retention
- No secrets in code — env vars or SSM only
- No emojis in code or docs

## Gotchas (don't relearn these)
1. PUT /photos must be an APIGW S3 service proxy, not a Lambda invoke
2. `x-amz-meta-customLabels` is graded — read it via headObject in LF1, merge with Rekognition output
3. CFN scope is narrow: ES, Lex, CodePipeline are explicitly out of T1
4. APIGW REST (not HTTP) — needed for SDK gen + API key + AWS service proxy
5. OpenSearch domain is the only meaningful cost — tear it down between sessions if a week-long uptime isn't acceptable

## Idle update protocol
Update CLAUDE.md, README.md, HANDOVER.md only at phase transitions. Use Edit (diff), not Write (rewrite).
Keep this file under 100 lines.
