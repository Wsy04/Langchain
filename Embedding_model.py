import os
import time
from contextlib import contextmanager

from chromadb.config import Settings
from dotenv import load_dotenv
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_ollama import OllamaEmbeddings
from langchain_openai import ChatOpenAI

load_dotenv()


def get_env(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        return ""
    return value.strip().strip('"').strip("'")


@contextmanager
def disable_proxy_temporarily():
    proxy_keys = [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ]
    old_env = {key: os.environ.get(key) for key in proxy_keys}
    try:
        for key in proxy_keys:
            os.environ.pop(key, None)
        yield
    finally:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def retry_ollama_call(func, retries: int = 3, delay: int = 2):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            return func()
        except Exception as exc:
            last_error = exc
            print(f"Ollama 调用失败，第 {attempt}/{retries} 次重试：{type(exc).__name__} {exc}")
            if attempt < retries:
                time.sleep(delay)
    raise last_error


def unique_documents(docs):
    seen_ids = set()
    unique_docs = []
    for doc in docs:
        doc_id = doc.metadata.get("id")
        if doc_id in seen_ids:
            continue
        seen_ids.add(doc_id)
        unique_docs.append(doc)
    return unique_docs


embedding_model_name = get_env("EMBEDDING_MODEL")
deepseek_api_key = get_env("DEEPSEEK_API_KEY")
deepseek_base_url = get_env("DEEPSEEK_API_BASE_URL")

documents = [
    Document(
        page_content="项目名称：智能简历问答系统。项目目标是将简历中的项目经历、技能栈和成果整理为可检索知识库。",
        metadata={"source": "项目概述", "id": 1},
    ),
    Document(
        page_content="技术栈包括 LangChain、Chroma、Ollama、本地嵌入模型和 DeepSeek 对话模型。",
        metadata={"source": "技术栈", "id": 2},
    ),
    Document(
        page_content="系统流程包括：准备知识片段、向量化、相似度检索、拼接上下文，再调用大模型生成最终回答。",
        metadata={"source": "系统流程", "id": 3},
    ),
    Document(
        page_content="工程优化包括：处理 .env 配置格式问题、检查 Ollama 模型是否存在、降低问答过程中的幻觉风险。",
        metadata={"source": "工程优化", "id": 4},
    ),
    Document(
        page_content="项目价值是快速验证一个最小可运行的 RAG 示例，适合作为课程作业、简历项目或知识库问答 Demo。",
        metadata={"source": "项目价值", "id": 5},
    ),
]

print("当前 EMBEDDING_MODEL =", embedding_model_name)

if not embedding_model_name:
    raise ValueError("EMBEDDING_MODEL 为空，请先检查 .env")

question = "请总结这个项目的目标、技术栈和优化点。"

with disable_proxy_temporarily():
    print("已临时禁用代理，开始访问本地 Ollama...")
    embedding_model = OllamaEmbeddings(model=embedding_model_name)

    print("\n开始构建向量库...")
    vectorstore = retry_ollama_call(
        lambda: Chroma.from_documents(
            documents=documents,
            embedding=embedding_model,
            collection_name="resume_project_demo",
            client_settings=Settings(anonymized_telemetry=False),
        )
    )

    retriever = vectorstore.as_retriever(search_type="mmr", search_kwargs={"k": 3, "fetch_k": 5})
    retrieval_queries = [
        question,
        "这个项目的目标是什么？",
        "这个项目的技术栈是什么？",
        "这个项目的优化点是什么？",
    ]
    retrieved_docs = []
    for retrieval_query in retrieval_queries:
        docs_for_query = retry_ollama_call(lambda q=retrieval_query: retriever.invoke(q))
        retrieved_docs.extend(docs_for_query)
    retrieved_docs = unique_documents(retrieved_docs)

print("\n已恢复代理配置。")
print("\n检索到的文档：")
context_text = ""
for index, doc in enumerate(retrieved_docs, start=1):
    line = f"[片段{index}] {doc.metadata.get('source', '未知来源')}：{doc.page_content}"
    print(line)
    context_text += line + "\n"

if not deepseek_api_key or not deepseek_base_url:
    print("\n未检测到完整的 DeepSeek 配置，先跳过大模型问答。")
else:
    print("\n开始调用 DeepSeek...")
    llm = ChatOpenAI(
        model="deepseek-chat",
        api_key=deepseek_api_key,
        base_url=deepseek_base_url,
        temperature=0,
    )

    prompt = PromptTemplate.from_template(
        """请严格根据以下已知信息回答问题。如果无法从已知信息中找到答案，请回答“根据已有信息无法回答”。

已知信息：
{context}

问题：{question}
回答："""
    )

    final_prompt = prompt.format(context=context_text, question=question)

    try:
        response = llm.invoke(final_prompt)
        print("\n问答结果：")
        print(response.content)
    except Exception as exc:
        print("\nDeepSeek 调用失败：")
        print(type(exc).__name__, str(exc))
