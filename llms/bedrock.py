import os
from dotenv import load_dotenv
from langchain_aws import ChatBedrockConverse

class BedrockLLM:
    def __init__(self):
        load_dotenv()

    def get_llm(self, model_name="apac.amazon.nova-lite-v1:0"):

        try:

            # os.environ["AWS_ACCESS_KEY_ID"] = os.getenv("AWS_ACCESS_KEY_ID")
            # os.environ["AWS_SECRET_ACCESS_KEY"] = os.getenv("AWS_SECRET_ACCESS_KEY")
            # os.environ["AWS_DEFAULT_REGION"] = os.getenv("AWS_DEFAULT_REGION")


            # print(f"AWS_ACCESS_KEY_ID: {os.environ["AWS_ACCESS_KEY_ID"]}")

            llm = ChatBedrockConverse(
                model_id=model_name,
                region_name="ap-southeast-1",
                provider="anthropic",

            )

            return llm
        except Exception as e:
            raise ValueError("Error occurred with exception: {e}")

        