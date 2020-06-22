#!/usr/bin/env bash
sam build -t template.yaml

sam deploy \
    --template-file ./.aws-sam/build/template.yaml \
    --stack-name $2 \
    --capabilities CAPABILITY_IAM \
    --parameter-overrides IncomingEmailAddress=$3 \
    --s3-bucket $4 \\
    --region $1