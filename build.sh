#!/usr/bin/env bash
# stop at the first failed step so a failed build/push never "updates" the runtime with the old image
set -euo pipefail

# build image
docker build -t 792682046440.dkr.ecr.ap-southeast-1.amazonaws.com/vendor-portal-ai --platform=linux/arm64 . --no-cache

# login to ecr
aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin 792682046440.dkr.ecr.ap-southeast-1.amazonaws.com

# push to ecr
docker push 792682046440.dkr.ecr.ap-southeast-1.amazonaws.com/vendor-portal-ai:latest


# update the agentcore runtime
aws bedrock-agentcore-control update-agent-runtime \
    --agent-runtime-id "vendor_portal_agent-MMif2PAgib" \
    --agent-runtime-artifact '{"containerConfiguration": {"containerUri": "792682046440.dkr.ecr.ap-southeast-1.amazonaws.com/vendor-portal-ai:latest"}}' \
    --role-arn "arn:aws:iam::792682046440:role/service-role/AmazonBedrockAgentCoreRuntimeDefaultServiceRole-sdjtg" \
    --network-configuration '{"networkMode": "PUBLIC"}' \
    --region="ap-southeast-1" \
    --environment-variables '{"DB_SECRET_ID": "arn:aws:secretsmanager:ap-southeast-1:792682046440:secret:agentcore/vendor-portal-agent/db-xl8bqA"}'