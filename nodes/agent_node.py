
from pydantic import BaseModel, Field
from typing import Annotated, Sequence, Literal
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from app.tools.retriever import retriever_tool
from app.tools.math_operations import add, multiply
from app.tools.web_browse import get_tools, create_tool_node
from app.tools.wikisearch import wikisearch
from app.llms.groq import GroqLLM
from app.llms.bedrock import BedrockLLM

class AgentNode:

    def __init__(self):
        
        # self.llm = GroqLLM().get_llm()
        self.llm = BedrockLLM().get_llm()

        


    def invoke_agent(self, state):
        """
            Invokes the agent model to generate a response based on the current state. Given the question, it will
            decide to retrieve using the retriever tool, or simply end.
            Args:
                state (messages): The current state
            Returns:
                dict: The updated state with the agent response appended to messages
        """
        print("---CALL AGENT--")

        messages = state["messages"]

        # model = model.bind_tools(tools)

        llm_with_tools = self.llm.bind_tools([retriever_tool(), add, multiply, get_tools()])

        response = llm_with_tools.invoke(messages)

        return {"messages": [response]}


    def grade_documents(self, state) -> Literal["generate","rewrite"]:
        """
            Determines whether the retrieved documents are relevant to the question.
            Args:
                state (messages): The current state
            Returns:
                str: A decision for whether the documents are relevant or not
        """

        print("--CHECK RELEVANCE--")

        # Data model
        class grade(BaseModel):
            """Binary score for relevance check."""
            binary_score: str = Field(description="Relevance score 'yes' or 'no'")


        ## LLM with tool and validation
        llm_with_tool = self.llm.with_structured_output(grade)

        # Prompt
        prompt=PromptTemplate(
            template="""You are a grader assessing relevance of a retrieved document to a user question. \n
                Here is the retrieved document: \n\n {context} \n\n
                Here is the user question: {question} \n
                If the document contains keyword(s) or semantic meaning related to the user question, grade it as relevant. \n
                Give a binary score 'yes' or 'no' score to indicate whether the document is releavant to the question.
            """,
            input_variables=["context", "question"],
        )

        # Chain
        chain = prompt | llm_with_tool
        messages = state["messages"]
        last_message = messages[-1]

        question=messages[0].content
        docs=last_message.content

        scored_result=chain.invoke({"question": question, "context":docs})

        score = scored_result.binary_score

        if score == "yes":
            print("---DECISION: DOCS RELEVANT---")
            return "generate"
        else:
            print("---DECISION: DOCS NOT RELEVANT---")
            print(score)
            return "rewrite"


    def rewrite(self, state):
        """
        Transform the query to produce a better question.
        Args:
            state (messages): The current state
        Returns:
            dict: The updated state with re-phrased question
        """
        print("---TRANSFORM QUERY---")
        messages = state["messages"]
        question = messages[0].content
        msg = [
            HumanMessage(
                content=f""" \n
                    Look at the input and try to reason about the underlying semantic intent / meaning. \n
                    Here is the initial question:
                    \n ------- \n
                    {question}
                    \n ------- \n
                    Formulate an improved question: 
                """,
            )
        ]
        # Grader
        response = self.llm.invoke(msg)
        return {"messages": [response]}

    def generate(self, state):
        """
            Generate answer
            Args:
                state (messages): The current state
            Returns:
                dict: The updated message
        """
        print("---GENERATE---")
        messages = state["messages"]
        question = messages[0].content
        last_message=messages[-1]

        docs=last_message.content

        # Prompt
        prompt = ChatPromptTemplate.from_messages([
            ("human", """You are an assistant for question-answering tasks. Use the following pieces of retrieved context to answer the question. If you don't know the answer, just say that you don't know. Use three sentences maximum and keep the answer concise.
        Question: {question} 
        Context: {context} 
        Answer:""")
        ])


        # Post-processing
        def format_docs(docs):
            return "\n\n".join(doc.page_content for doc in docs)

        # Chain
        rag_chain = prompt | self.llm | StrOutputParser()

        # Run
        response = rag_chain.invoke({"context":docs, "question": question})

        return {"messages": [response]}