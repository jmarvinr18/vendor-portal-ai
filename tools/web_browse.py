# from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_tavily import TavilySearch
from langgraph.prebuilt import ToolNode
from dotenv import load_dotenv
from config import load_secrets

load_dotenv()
load_secrets()

def browse(query: str):
    """
    Search the web for up-to-date information and return the top results (with images).
    Use this for current events or anything not found in the internal documents.
    """

    print(f"QUERY FOR BROWSING: {query}")

    tool = TavilySearch(max_results=2, include_images=True)


    return tool.invoke({"query": query})

def create_tool_node(tools):
    """
    Creates and returns a tool node for the graph
    """
    return ToolNode(tools=tools)