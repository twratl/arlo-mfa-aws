#!/usr/bin/env bash
sam build -t template.yaml

sam deploy \
    --template-file ./.aws-sam/build/template.yaml \
    --stack-name $1 \
    --capabilities CAPABILITY_IAM \
    --parameter-overrides IncomingEmailAddress=$2 \
    --s3-bucket $3