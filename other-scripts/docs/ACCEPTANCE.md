# Acceptance Criteria — Evidence

Each row maps to the acceptance criteria in the assignment PDF (page 4-5).

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | CFN template (T1) creates the required resources | PASS | `aws cloudformation deploy --template-file other-scripts/cfn/template.yaml --stack-name cc-photos-stack --capabilities CAPABILITY_NAMED_IAM` succeeded; outputs visible in `aws cloudformation describe-stacks --stack-name cc-photos-stack`. Stack contains both Lambdas, APIGW, both buckets, IAM roles, API key + usage plan. |
| 2 | New commit -> CodePipeline -> deploys to AWS infra | PENDING | GitHub repos not yet created. `other-scripts/pipelines/buildspec-backend.yml` and `other-scripts/pipelines/buildspec-frontend.yml` are ready to wire once repos exist. See HANDOVER.md for the manual step. |
| 3 | `x-amz-meta-customLabels` feature works end-to-end | PASS | Uploaded `dog.jpg` with header `x-amz-meta-customLabels: Sam, Sally`. ES doc shows `labels: [..., 'sam', 'sally']`. Search `q=show me sally` returns the photo. |
| 4 | Search returns photo for any of its Rekognition labels | PASS | `dog.jpg` Rekognition labels: animal, canine, dog, mammal, pet, puppy, labrador retriever. Confirmed `q=dog`, `q=show me dogs`, `q=find pets and water` all match. |
| 4a | Search by custom label returns matching photos | PASS | `q=show me sally` -> dog.jpg only (the only photo tagged `sally`). |
| 5 | All other functionality working | PASS | Frontend at the S3 website URL renders, search box returns photos, upload form sends the custom-labels header, results grid displays thumbnails. |

## Verification commands (reproducible)

```bash
# 1. CFN resources exist
aws cloudformation describe-stack-resources --stack-name cc-photos-stack \
  --region us-east-1 --profile nyu --query 'StackResources[].LogicalResourceId'

# 3-4. End-to-end through APIGW
API=$(aws cloudformation describe-stacks --stack-name cc-photos-stack --query "Stacks[0].Outputs[?OutputKey=='ApiInvokeUrl'].OutputValue" --output text --profile nyu)
KEY_ID=$(aws cloudformation describe-stacks --stack-name cc-photos-stack --query "Stacks[0].Outputs[?OutputKey=='ApiKeyId'].OutputValue" --output text --profile nyu)
KEY=$(aws apigateway get-api-key --api-key "$KEY_ID" --include-value --query value --output text --profile nyu)
curl -X PUT "$API/photos/cc-photos-storage-746140163942/test.jpg" \
  -H "x-api-key: $KEY" -H "Content-Type: image/jpeg" \
  -H "x-amz-meta-customLabels: Tag1, Tag2" \
  --data-binary @some-photo.jpg
sleep 6
curl -G "$API/search" --data-urlencode "q=show me tag1" -H "x-api-key: $KEY"
```

## Demo flow recorded in HANDOVER.md "Demo script" section.
