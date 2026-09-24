from states.blogstate import BlogState
from langchain_core.messages import SystemMessage, HumanMessage
from states.blogstate import Blog

class BlogNode:
    """
    A class to represent the blog node
    """

    def __init__(self,llm):
        self.llm = llm

    def title_creation(self, state: BlogState):
        """
        Create the title for the blog
        """

        if "topic" in state and state["topic"]:
            prompt = """
                     You are an expert blog content writer. Use Markdown formatting. Generate
                     a blog title for the {topic}. This title should be creative and SEO friendly
                     """

            system_message = prompt.format(topic=state["topic"])

            title = self.llm.invoke(system_message).content


            return {"blog": {"title": title}}

    def content_generation(self,state: BlogState):

        if "topic" in state and state["topic"]:
            prompt = """You are an expert blog content writer. Use Markdown formatting. Generate a data
                     blog content with detailed breakdown for the {topic}
                     """
            system_message = prompt.format(topic=state["topic"])
            response = self.llm.invoke(system_message)

            return {"blog": {"title": state["blog"]["title"], "content": response.content}}


    def translation(self,state: BlogState):
        """
        Translate the blog to the specified language
        """
        if "current_language" in state and state["current_language"]:
            prompt = """
                     You are an expert {current_language} translator. Translate the following blog content to {current_language}.
                     - Maintain the original tone, style and formatting.
                     - Adapt cultural references and idioms to be appropriate for {current_language}
                     Blog Title: {title}
                     Blog Content: {content}
                     """

            system_message=[HumanMessage(prompt.format(
                current_language=state["current_language"],
                title=state["blog"]["title"],
                content=state["blog"]["content"]
            ))]

            translated_blog = self.llm.with_structured_output(Blog).invoke(system_message)

            return {"blog": {"title": state["blog"]["title"], "content": translated_blog.content}}

    def route(self, state: BlogState):

        return {"current_language": state["current_language"]}

    def route_decision(self, state: BlogState):
        """
        Route the content to the respective translation function.
        """

        if state["current_language"]=="hindi":
            return "hindi"
        elif state["current_language"]=="french":
            return "french"