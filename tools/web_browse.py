from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.prebuilt import ToolNode
from app.config import load_secrets
load_secrets()

def get_tools():
    """
    Return the list of tools to be used in the chatbot
    """
    return TavilySearchResults(max_results=2, include_images=True)

def create_tool_node(tools):
    """
    Creates and returns a tool node for the graph
    """
    return ToolNode(tools=tools)