from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import WebBaseLoader
# from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv
load_dotenv()




def load_document_from_web_url():

    urls = [
        "https://www.deszr.com/"
    ]

    docs= [WebBaseLoader(url).load() for url in urls]
    doc_list = [doc for sublist in docs for doc in sublist]


    print(f"DOC LIST: {doc_list}")

    return doc_list


def recursive_split_text():
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    docs_splits = text_splitter.split_documents(load_document_from_web_url())

    return docs_splits


def create_faiss_retriever():

    vectorstore = FAISS.from_documents(
        documents=recursive_split_text(),
        embedding=OpenAIEmbeddings()
    )
    return vectorstore


def get_retriever():
    faiss_vectorstore = create_faiss_retriever()
    retriever = faiss_vectorstore.as_retriever()
    return retriever
