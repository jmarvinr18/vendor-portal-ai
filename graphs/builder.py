# from dotenv import load_dotenv
# load_dotenv()

from app.config import load_secrets
load_secrets()

from langgraph.graph import StateGraph, START, END
from app.llms.groq import GroqLLM
from app.states.agentstate import AgentState
from app.nodes.agent_node import AgentNode
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt import tools_condition
from app.tools.retriever import retriever_tool
from app.tools.math_operations import add, multiply
from app.tools.web_browse import get_tools, create_tool_node
from app.tools.wikisearch import wikisearch
from IPython.display import Image, display
from app.llms.bedrock import BedrockLLM
from langgraph.checkpoint.memory import MemorySaver


class GraphBuilder:
    def __init__(self, llm):

        self.graph = StateGraph(AgentState)

        self.llm = llm

    def build_graph(self):
        """
        Build a graph to generate blogs based on topic
        """

        self.agent_node_obj = AgentNode()

        # Nodes
        # Define the nodes we will cycle between
        self.graph.add_node("agent", self.agent_node_obj.invoke_agent)

        # agent
        toolnode = ToolNode(
            [retriever_tool(), add, multiply, get_tools()], handle_tool_errors=True)

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

    def setup_graph(self):
        self.build_graph()

        return self.graph.compile(checkpointer=MemorySaver())


## Below code is for the langsmith, langgraph studio
llm=BedrockLLM().get_llm()

# get the graph
graph_builder = GraphBuilder(llm)
graph = graph_builder.build_graph().compile()
