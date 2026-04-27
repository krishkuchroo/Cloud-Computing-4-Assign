# Architecture

## High-level diagram (per assignment annex)

```
                        +-----------------+
                        | Frontend (B1)   |   static-hosted HTML/JS
                        | s3-website      |
                        +--------+--------+
                                 | API call (x-api-key)
                                 v
                        +-----------------+
                        | API Gateway     |   REST, prod stage
                        | cc-photos-api   |
                        +---+---------+---+
              PUT /photos    |         | GET /search
              S3 service     |         | Lambda proxy
              proxy          |         |
                             v         v
+---------------+     +-------------+   +-----------------+    +-----------+
| S3 (B2)       |<----| s3:PutObj   |   | Lambda LF2      |--->| Lex V2    |
| photos        |     |             |   | search-photos   |    | search    |
| storage       |     +-------------+   |                 |    | bot       |
+-------+-------+                       +--------+--------+    +-----------+
        |                                        |
        | s3:ObjectCreated:*                     | terms query on labels
        v                                        v
+---------------+     +-------------+    +-----------------+
| Lambda LF1    |---->| Rekognition |    |   OpenSearch    |
| index-photos  |     | DetectLabels|    |   "photos" idx  |
|               |     +-------------+    |   t3.small.search|
|  headObject   |                        +-----------------+
|  for custom   |                                ^
|  labels       |--------------------------------+
+---------------+        SigV4 PUT _doc/{key}
```

## Sequence: upload

1. Browser -> APIGW `PUT /photos/{bucket}/{key}` with `x-api-key`, `Content-Type`, optional `x-amz-meta-customLabels`.
2. APIGW S3-proxy method assumes `cc-photos-apigw-s3-role` and forwards the body to `s3:PutObject` on B2, preserving the custom-labels header as object metadata.
3. S3 fires `ObjectCreated` notification to LF1.
4. LF1: `rekognition:DetectLabels` (max 20, conf >= 70), then `s3:HeadObject` for `x-amz-meta-customLabels`. Lowercases + dedupes both lists into a single labels array.
5. LF1 SigV4-signs and PUTs the document to `OpenSearch /photos/_doc/{url-encoded-key}`. Document id = key, so re-uploads overwrite (idempotent).

## Sequence: search

1. Browser -> APIGW `GET /search?q=...` with `x-api-key`.
2. APIGW Lambda-proxy invokes LF2.
3. LF2: `lexv2-runtime:RecognizeText` against `cc-photos-search-bot` `prod` alias. Pulls `keyword1` / `keyword2` slot values from the SearchIntent response. Falls back to stopword-filtered tokenization if Lex returns no slots.
4. Cheap plural-stripping stemmer (e.g. `dogs` -> `dog`) for query coverage.
5. SigV4-signed POST to `OpenSearch /photos/_search` with a `terms` query on `labels`.
6. Response: `{results: [{url, labels}]}`. URLs point at the public B2 object endpoint.

## Why these choices

- **`labels` mapping is `keyword`, not `text`.** The acceptance criterion requires every Rekognition label to independently retrieve the photo. `keyword` + `terms` query is exact-match across the array, which is what we want. `text` + `match` would tokenize and skew scoring.
- **Document id = object key.** Re-uploading `dog.jpg` overwrites instead of duplicating, which is the natural "edit photo metadata" behavior.
- **APIGW S3 proxy, not a Lambda for upload.** Avoids paying Lambda for every upload, and per spec.
- **Lex slots `keyword1` and `keyword2` both Optional.** Required slots cause Lex to prompt for the missing value, which breaks single-shot search via API.
- **Cheap stemmer in LF2.** Real stemming would need an analyzed `text` field on labels, which would invalidate (1). Trailing-`s` stripping is correct for >95% of English plurals seen in Rekognition output.
- **CFN scope is narrow** (Lambdas + APIGW + 2 buckets) per spec note 7.b. OpenSearch, Lex, CodePipeline are out of CFN scope.

## Resources by service

| Service | Resource | Identifier |
|---|---|---|
| S3 | B1 frontend | `cc-photos-frontend-746140163942` |
| S3 | B2 photos | `cc-photos-storage-746140163942` |
| Lambda | LF1 | `index-photos` |
| Lambda | LF2 | `search-photos` |
| OpenSearch | Domain | `photos` (`t3.small.search`, 1 node, 10 GB gp3) |
| OpenSearch | Index | `photos` (mapping in `other-scripts/es/index_mapping.json`) |
| Lex V2 | Bot | `cc-photos-search-bot` (id `T4DPQ3XVUE`, alias `UJABDDPGRP`) |
| API Gateway | REST API | `cc-photos-api`, stage `prod` |
| CloudFormation | Stack | `cc-photos-stack` |
| IAM | LF1 role | `cc-photos-lf1-role` |
| IAM | LF2 role | `cc-photos-lf2-role` |
| IAM | APIGW->S3 role | `cc-photos-apigw-s3-role` |
| IAM | Lex runtime role | `cc-photos-lex-runtime-role` |
