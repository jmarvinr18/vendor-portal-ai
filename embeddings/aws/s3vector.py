from langchain_aws.retrievers import AmazonKnowledgeBasesRetriever
from dotenv import load_dotenv
import boto3
from botocore.config import Config

load_dotenv()


def get_retriever():

    kb_client = boto3.client(
        "bedrock-agent-runtime",
        region_name="ap-southeast-1",
        config=Config(
            retries={"max_attempts": 6, "mode": "adaptive"},  # standard also fine
            tcp_keepalive=True,      # detect dead sockets instead of reusing them
            connect_timeout=5,
            read_timeout=30,
            max_pool_connections=10,
        ),
    )    
    retriever = AmazonKnowledgeBasesRetriever(
        knowledge_base_id="DTDQDQUF9E",
        client=kb_client,
        region_name="ap-southeast-1",
        retrieval_config={
            "vectorSearchConfiguration": {"numberOfResults": 10}
        },        
    )
    return retriever
