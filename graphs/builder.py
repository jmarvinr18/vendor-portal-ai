# from dotenv import load_dotenv
# load_dotenv()

# from config import load_secrets
# load_secrets()
import os
from langgraph.graph import StateGraph, START, END
# from llms.groq import GroqLLM
from states.agentstate import AgentState
from nodes.agent_node import AgentNode
from langgraph.prebuilt import ToolNode
from tools.retriever import retriever_tool
from tools.math_operations import add, multiply
from tools.web_browse import browse, create_tool_node
from tools.wikisearch import wikisearch

from langgraph.prebuilt import tools_condition
from llms.bedrock import BedrockLLM
from langgraph.checkpoint.memory import MemorySaver
from langchain_mcp_adapters.client import MultiServerMCPClient

class GraphBuilder:
    def __init__(self, llm):

        self.graph = StateGraph(AgentState)

        self.llm = llm

    async def build_graph(self):
        """
        Build a graph to generate blogs based on topic
        """

        client = MultiServerMCPClient({
            "pg-tools": {
                "transport": "streamable_http",
                "url": os.getenv("PG_TOOLS_MCP_URL", "http://host.docker.internal:54901/mcp"),
            },
            "devsecops": {
                "transport": "streamable_http",
                "url": os.getenv("DEVSECOPS_MCP_URL", "http://host.docker.internal:59229/mcp"),
            }            

        })      

        mcp_tools = await client.get_tools()  

        print(f"TOOLS: {mcp_tools}")

        self.agent_node_obj = AgentNode(mcp_tools + [retriever_tool(), add, multiply, browse()])

        # Nodes
        # Define the nodes we will cycle between
        self.graph.add_node("agent", self.agent_node_obj.invoke_agent)

        # agent
        toolnode = ToolNode(mcp_tools + [retriever_tool(), add, multiply, browse()], handle_tool_errors=True)
        

        self.graph.add_node("retrieve_tool", toolnode)

        # retrieval
        # Re-writing the question
        self.graph.add_node("rewrite", self.agent_node_obj.rewrite)
        self.graph.add_node("generate", self.agent_node_obj.generate)

        # Generating a response after we know the documents are relevant
        # Call agent node to decide to retrieve or not
        self.graph.add_edge(START, "agent")

        # Decide whether to retrieve
        self.graph.add_conditional_edges("agent",
                                         # Assess agent decision
                                         tools_condition,
                                         {
                                             # Translate the condition outputs to nodes in our graph
                                             "tools": "retrieve_tool",
                                             END: END,
                                         }
                                         )
        # Edges taken after the `action` node is called.
        self.graph.add_conditional_edges(
            "retrieve_tool", self.agent_node_obj.grade_documents)
        self.graph.add_edge("generate", END)
        self.graph.add_edge("rewrite", "agent")

        return self.graph

    async def setup_graph(self):
        await self.build_graph()

        return self.graph.compile(checkpointer=MemorySaver())


## Below code is for the langsmith, langgraph studio
## (point langgraph.json at "graphs/builder.py:make_graph")
async def make_graph():
    graph_builder = GraphBuilder(BedrockLLM().get_llm())
    await graph_builder.build_graph()
    return graph_builder.graph.compile()
