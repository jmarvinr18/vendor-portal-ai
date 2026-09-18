from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper

def wikisearch():
    """
    Search wikipedia about the information
    """
    api_wrapper_arxiv = WikipediaAPIWrapper(top_k_results=1,doc_content_chars_max=2000)

    wiki = WikipediaQueryRun(api_wrapper=api_wrapper_arxiv)

    return wiki
    