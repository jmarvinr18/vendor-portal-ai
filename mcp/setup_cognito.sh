#!/usr/bin/env bash
: "${REGION:?}" "${USERNAME:?}" "${PASSWORD:?}"

export POOL_ID=$(aws cognito-idp create-user-pool \
  --pool-name "mcp-agentcore-pool" \
  --policies '{"PasswordPolicy":{"MinimumLength":8}}' \
  --region "$REGION" --query 'UserPool.Id' --output text)

export CLIENT_ID=$(aws cognito-idp create-user-pool-client \
  --user-pool-id "$POOL_ID" \
  --client-name "mcp-client" \
  --no-generate-secret \
  --explicit-auth-flows ALLOW_USER_PASSWORD_AUTH ALLOW_REFRESH_TOKEN_AUTH \
  --region "$REGION" --query 'UserPoolClient.ClientId' --output text)

aws cognito-idp admin-create-user --user-pool-id "$POOL_ID" \
  --username "$USERNAME" --message-action SUPPRESS --region "$REGION" > /dev/null
aws cognito-idp admin-set-user-password --user-pool-id "$POOL_ID" \
  --username "$USERNAME" --password "$PASSWORD" --permanent --region "$REGION" > /dev/null

export BEARER_TOKEN=$(aws cognito-idp initiate-auth \
  --client-id "$CLIENT_ID" --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME="$USERNAME",PASSWORD="$PASSWORD" \
  --region "$REGION" --query 'AuthenticationResult.AccessToken' --output text)

export DISCOVERY_URL="https://cognito-idp.$REGION.amazonaws.com/$POOL_ID/.well-known/openid-configuration"
echo "POOL_ID=$POOL_ID"; echo "CLIENT_ID=$CLIENT_ID"; echo "DISCOVERY_URL=$DISCOVERY_URL"


aws cognito-idp initiate-auth \
  --client-id "$CLIENT_ID" --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME="$USERNAME",PASSWORD="$PASSWORD" \
  --region "$REGION" --query 'AuthenticationResult.AccessToken' --output text