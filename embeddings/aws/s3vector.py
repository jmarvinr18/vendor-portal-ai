from langchain_aws.retrievers import AmazonKnowledgeBasesRetriever
from dotenv import load_dotenv
load_dotenv()


def get_retriever():
    retriever = AmazonKnowledgeBasesRetriever(
        knowledge_base_id="DTDQDQUF9E",
        region_name="ap-southeast-1",
        retrieval_config={
            "vectorSearchConfiguration": {"numberOfResults": 4}
        },        
    )
    return retriever
