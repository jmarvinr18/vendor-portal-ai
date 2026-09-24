from langchain_core.tools.retriever import create_retriever_tool
from embeddings.aws.s3vector import get_retriever
# from embeddings.local.faiss import get_retriever

def retriever_tool():
    """
    Retrieve from the vector store.
    Use this to look up information from the Langchain blog.
    """

    retriever_tool_langchain = create_retriever_tool(
        get_retriever(),
        "retriever_vector_langchain_blog",
        "Search and run information about Langchain"
    )

    # print(f"RETRIEVER TOOL RESPONSE: {retriever_tool_langchain}")

    return retriever_tool_langchain


# def aws_retriever():

#     bedrock_config = Config(
#         connect_timeout=120,
#         read_timeout=120,
#         retries={"max_attempts": 3}
#     )
#     # bedrock-agent-runtime is what the retriever uses to call your KB
#     bedrock_agent_client = boto3.client(
#         "bedrock-agent-runtime",
#         region_name="ap-southeast-1",
#         config=bedrock_config
#     )
#     # --- Retriever pointing directly at your Bedrock Knowledge Base ---
#     aws_bedrock_retriever = AmazonKnowledgeBasesRetriever(
#         knowledge_base_id="DTDQDQUF9E",        # from AWS Bedrock console
#         client=bedrock_agent_client,           # explicit client
#         retrieval_config={
#             "vectorSearchConfiguration": {
#                 "numberOfResults": 5,
#                 "overrideSearchType": "SEMANTIC"   # or HYBRID
#             }
#         },
#     )

#     print(f"AWS_RETRIEVER: {aws_bedrock_retriever}")

#     return aws_bedrock_retriever
