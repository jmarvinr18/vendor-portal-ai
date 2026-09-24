# agent.py
from bedrock_agentcore.runtime import BedrockAgentCoreApp

from graphs.builder import GraphBuilder   # your existing graph
from llms.bedrock import BedrockLLM
from streaming import stream_answer
# from config import load_secrets
# load_secrets()
app = BedrockAgentCoreApp()



llm = BedrockLLM().get_llm()
graph = GraphBuilder(llm).setup_graph()

@app.entrypoint
async def invoke(payload, context):

    print(f"PAYLOAD: {payload}")

    inputs = {"messages": [{"role": "user", "content": payload["message"]}]}
    config = {"configurable": {"thread_id": context.session_id}}

    # Returning an async generator makes AgentCore answer with text/event-stream.
    # Send {"stream": false} for the old single JSON response.
    if payload.get("stream", True):
        return stream_answer(graph, inputs, config, model=llm.model_id)

    result = await graph.ainvoke(inputs, config=config)
    return {
        "result": result["messages"][-1].content,
        "messages": [m.model_dump(mode="json") for m in result["messages"]],
    }

if __name__ == "__main__":
    app.run()