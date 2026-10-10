import boto3
import json
import uuid
client = boto3.client('bedrock-agentcore', region_name='ap-southeast-1')
payload = json.dumps({"message": "Explain machine learning in simple terms"})

response = client.invoke_agent_runtime(
    agentRuntimeArn='arn:aws:bedrock-agentcore:ap-southeast-1:792682046440:runtime/vendor_portal_agent-MMif2PAgib',
    runtimeSessionId=str(uuid.uuid4()), # Must be 33+ char. Every new SessionId will create a new MicroVM
    payload=payload
)
response_body = response['response'].read()
print(response_body)
# response_data = json.loads(response_body)
# print("Agent Response:", response_data)