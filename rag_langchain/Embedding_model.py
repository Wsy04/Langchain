import base64
import os
import re
import time
import unicodedata
import zipfile
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from threading import Lock
from xml.etree import ElementTree

import uvicorn
from chromadb.config import Settings
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_ollama import OllamaEmbeddings
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from pypdf import PdfReader

try:
    import fitz
except ImportError:
    fitz = None

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


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


def unique_documents(docs: list[Document]) -> list[Document]:
    seen_ids = set()
    unique_docs = []
    for doc in docs:
        doc_id = doc.metadata.get("id")
        if doc_id in seen_ids:
            continue
        seen_ids.add(doc_id)
        unique_docs.append(doc)
    return unique_docs


def serialize_document(doc: Document) -> dict:
    file_type = doc.metadata.get("file_type")
    return {
        "id": doc.metadata.get("id"),
        "source": doc.metadata.get("source", "未知来源"),
        "content": doc.page_content,
        "file_name": doc.metadata.get("file_name"),
        "file_type": file_type,
        "show_in_knowledge_base": file_type != "pdf",
    }


def decode_text_bytes(file_bytes: bytes) -> str:
    encodings = ["utf-8", "utf-8-sig", "gbk", "gb18030", "utf-16"]
    for encoding in encodings:
        try:
            return file_bytes.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    raise ValueError("TXT 文件编码无法识别，请尽量使用 UTF-8 编码。")


def normalize_extracted_text(text: str) -> str:
    text = text.replace("\x00", "").replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def score_extracted_text(text: str) -> float:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return 0.0

    readable_chars = 0
    suspicious_chars = 0
    for char in compact:
        category = unicodedata.category(char)
        if "\u4e00" <= char <= "\u9fff":
            readable_chars += 3
        elif char.isascii() and (char.isalnum() or char in ".,;:!?%+-_/()[]{}@#&*'\""):
            readable_chars += 2
        elif category.startswith(("L", "N", "P")):
            readable_chars += 1
        else:
            suspicious_chars += 2

        if char in {"�", "□", "■", "◆"}:
            suspicious_chars += 5

    cid_penalty = len(re.findall(r"\(cid:\d+\)", text)) * 8
    content_bonus = min(len(compact), 1200) / 300
    return readable_chars - suspicious_chars - cid_penalty + content_bonus


def has_usable_pdf_text(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 40:
        return False
    if re.search(r"\(cid:\d+\)", text):
        return False
    return score_extracted_text(text) >= 120


def extract_text_with_pypdf(file_bytes: bytes, extraction_mode: str) -> str:
    reader = PdfReader(BytesIO(file_bytes))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text(extraction_mode=extraction_mode) or "")
    return normalize_extracted_text("\n".join(parts))


def extract_text_with_pymupdf(file_bytes: bytes) -> str:
    if fitz is None:
        return ""

    with fitz.open(stream=file_bytes, filetype="pdf") as pdf_document:
        parts = []
        for page in pdf_document:
            parts.append(page.get_text("text") or "")
    return normalize_extracted_text("\n".join(parts))


def extract_text_from_pdf(file_bytes: bytes) -> str:
    candidates = []

    for extraction_mode in ("layout", "plain"):
        try:
            text = extract_text_with_pypdf(file_bytes, extraction_mode=extraction_mode)
        except Exception:
            continue
        if text:
            candidates.append((f"pypdf:{extraction_mode}", text))

    try:
        pymupdf_text = extract_text_with_pymupdf(file_bytes)
    except Exception:
        pymupdf_text = ""
    if pymupdf_text:
        candidates.append(("pymupdf:text", pymupdf_text))

    if not candidates:
        raise ValueError("PDF 未提取到任何文本，可能是扫描件或图片版 PDF。")

    _, best_text = max(candidates, key=lambda item: score_extracted_text(item[1]))
    if not has_usable_pdf_text(best_text):
        raise ValueError(
            "PDF 提取结果不可用，可能是扫描版、字体映射异常或乱码文字层。建议先转成 DOCX/TXT，"
            "或使用带文字层/OCR 的 PDF 再上传。"
        )
    return best_text


def extract_text_from_docx(file_bytes: bytes) -> str:
    with zipfile.ZipFile(BytesIO(file_bytes)) as docx_zip:
        try:
            xml_content = docx_zip.read("word/document.xml")
        except KeyError as exc:
            raise ValueError("Word 文件缺少 document.xml，无法读取。") from exc

    root = ElementTree.fromstring(xml_content)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    paragraphs = []
    for paragraph in root.findall(".//w:p", namespace):
        texts = [node.text for node in paragraph.findall(".//w:t", namespace) if node.text]
        if texts:
            paragraphs.append("".join(texts))
    return "\n".join(paragraphs).strip()


def extract_text_from_file(file_name: str, file_bytes: bytes) -> tuple[str, str]:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".txt":
        return decode_text_bytes(file_bytes), "txt"
    if suffix == ".pdf":
        return extract_text_from_pdf(file_bytes), "pdf"
    if suffix == ".docx":
        return extract_text_from_docx(file_bytes), "docx"
    if suffix == ".doc":
        raise ValueError("当前仅支持 Word 的 .docx 格式，老式 .doc 暂不支持。")
    raise ValueError("仅支持上传 .txt、.pdf、.docx 文件。")


def split_text_into_chunks(text: str, chunk_size: int = 360) -> list[str]:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return []

    paragraphs = [paragraph.strip() for paragraph in cleaned.split("\n") if paragraph.strip()]
    chunks = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n{paragraph}"
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= chunk_size:
            current = paragraph
            continue
        start = 0
        while start < len(paragraph):
            chunks.append(paragraph[start : start + chunk_size])
            start += chunk_size
        current = ""
    if current:
        chunks.append(current)
    return chunks


EMBEDDING_MODEL_NAME = get_env("EMBEDDING_MODEL")
DEEPSEEK_API_KEY = get_env("DEEPSEEK_API_KEY")
DEEPSEEK_API_BASE_URL = get_env("DEEPSEEK_API_BASE_URL")

BASE_DOCUMENTS = [
    Document(
        page_content="项目名称：智能简历问答系统。项目目标是将简历中的项目经历、技能栈和成果整理为可检索知识库。",
        metadata={"source": "项目概述", "id": 1, "file_name": None, "file_type": "seed"},
    ),
    Document(
        page_content="技术栈包括 LangChain、Chroma、Ollama、本地嵌入模型和 DeepSeek 对话模型。",
        metadata={"source": "技术栈", "id": 2, "file_name": None, "file_type": "seed"},
    ),
    Document(
        page_content="系统流程包括：准备知识片段、向量化、相似度检索、拼接上下文，再调用大模型生成最终回答。",
        metadata={"source": "系统流程", "id": 3, "file_name": None, "file_type": "seed"},
    ),
    Document(
        page_content="工程优化包括：处理 .env 配置格式问题、检查 Ollama 模型是否存在、降低问答过程中的幻觉风险。",
        metadata={"source": "工程优化", "id": 4, "file_name": None, "file_type": "seed"},
    ),
    Document(
        page_content="项目价值是快速验证一个最小可运行的 RAG 示例，适合作为课程作业、简历项目或知识库问答 Demo。",
        metadata={"source": "项目价值", "id": 5, "file_name": None, "file_type": "seed"},
    ),
]

PROMPT = PromptTemplate.from_template(
    """请严格根据以下已知信息回答问题。如果无法从已知信息中找到答案，请回答“根据已有信息无法回答”。

已知信息：
{context}

问题：{question}
回答："""
)

DOCUMENTS = list(BASE_DOCUMENTS)
NEXT_DOCUMENT_ID = max(doc.metadata["id"] for doc in BASE_DOCUMENTS) + 1
DOCUMENTS_LOCK = Lock()
VECTORSTORE_LOCK = Lock()
VECTORSTORE = None


class AskRequest(BaseModel):
    question: str


class UploadRequest(BaseModel):
    file_name: str
    content_base64: str


def get_documents_snapshot() -> list[Document]:
    with DOCUMENTS_LOCK:
        return list(DOCUMENTS)


def get_next_document_id() -> int:
    global NEXT_DOCUMENT_ID
    with DOCUMENTS_LOCK:
        current = NEXT_DOCUMENT_ID
        NEXT_DOCUMENT_ID += 1
        return current


def invalidate_vectorstore() -> None:
    global VECTORSTORE
    with VECTORSTORE_LOCK:
        VECTORSTORE = None


def add_uploaded_documents(file_name: str, file_type: str, text: str) -> list[Document]:
    chunks = split_text_into_chunks(text)
    if not chunks:
        raise ValueError("文件内容为空，无法加入知识库。")

    created_docs = []
    total_chunks = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        source = file_name if total_chunks == 1 else f"{file_name}（片段 {index}/{total_chunks}）"
        created_docs.append(
            Document(
                page_content=chunk,
                metadata={
                    "source": source,
                    "id": get_next_document_id(),
                    "file_name": file_name,
                    "file_type": file_type,
                },
            )
        )

    with DOCUMENTS_LOCK:
        DOCUMENTS[:] = [
            doc for doc in DOCUMENTS if doc.metadata.get("file_name") != file_name
        ]
        DOCUMENTS.extend(created_docs)
    invalidate_vectorstore()
    return created_docs


def build_vectorstore() -> Chroma:
    if not EMBEDDING_MODEL_NAME:
        raise RuntimeError("EMBEDDING_MODEL 为空，请先检查 .env")

    docs_snapshot = get_documents_snapshot()
    collection_name = f"resume_project_demo_api_{int(time.time() * 1000)}"
    with disable_proxy_temporarily():
        embedding_model = OllamaEmbeddings(model=EMBEDDING_MODEL_NAME)
        return retry_ollama_call(
            lambda: Chroma.from_documents(
                documents=docs_snapshot,
                embedding=embedding_model,
                collection_name=collection_name,
                client_settings=Settings(anonymized_telemetry=False),
            )
        )


def get_vectorstore() -> Chroma:
    global VECTORSTORE
    if VECTORSTORE is None:
        with VECTORSTORE_LOCK:
            if VECTORSTORE is None:
                VECTORSTORE = build_vectorstore()
    return VECTORSTORE


def build_retrieval_queries(question: str) -> list[str]:
    queries = [
        question,
        "这个项目的目标是什么？",
        "这个项目的技术栈是什么？",
        "这个项目的优化点是什么？",
    ]
    return list(dict.fromkeys(query.strip() for query in queries if query.strip()))


def retrieve_documents(question: str) -> list[Document]:
    vectorstore = get_vectorstore()
    retriever = vectorstore.as_retriever(search_type="mmr", search_kwargs={"k": 3, "fetch_k": 5})

    with disable_proxy_temporarily():
        retrieved_docs = []
        for retrieval_query in build_retrieval_queries(question):
            docs_for_query = retry_ollama_call(lambda q=retrieval_query: retriever.invoke(q))
            retrieved_docs.extend(docs_for_query)
    return unique_documents(retrieved_docs)


def build_context_text(docs: list[Document]) -> str:
    lines = []
    for index, doc in enumerate(docs, start=1):
        lines.append(f"[片段{index}] {doc.metadata.get('source', '未知来源')}：{doc.page_content}")
    return "\n".join(lines)


def build_fallback_answer(question: str, docs: list[Document]) -> str:
    if not docs:
        return "根据已有信息无法回答。"

    by_source = {doc.metadata.get("source"): doc.page_content for doc in docs}
    parts = []
    wants_summary = "总结" in question or "概括" in question
    wants_goal = wants_summary or "目标" in question
    wants_stack = wants_summary or "技术栈" in question or "框架" in question
    wants_optimization = wants_summary or "优化" in question or "亮点" in question

    if wants_goal and any("项目概述" in source for source in by_source):
        parts.append("项目目标是将简历中的项目经历、技能栈和成果整理成可检索知识库。")
    if wants_stack and any("技术栈" in source for source in by_source):
        parts.append("技术栈主要包括 LangChain、Chroma、Ollama、本地嵌入模型和 DeepSeek 对话模型。")
    if wants_optimization and any("工程优化" in source for source in by_source):
        parts.append("优化点包括处理 .env 配置格式问题、检查 Ollama 模型状态，以及降低问答中的幻觉风险。")

    if parts:
        return "".join(parts)

    summary = "；".join(doc.page_content for doc in docs[:5])
    return f"根据检索到的内容，可以先得到这些信息：{summary}"


def call_deepseek(question: str, context_text: str) -> str:
    if not DEEPSEEK_API_KEY or not DEEPSEEK_API_BASE_URL:
        raise RuntimeError("DeepSeek 配置不完整。")

    llm = ChatOpenAI(
        model="deepseek-v4-flash",
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_API_BASE_URL,
        temperature=0,
    )
    final_prompt = PROMPT.format(context=context_text, question=question)
    response = llm.invoke(final_prompt)
    return response.content.strip()


app = FastAPI(title="智能简历问答系统 API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/static/styles.css")
def styles():
    return FileResponse(BASE_DIR / "styles.css", media_type="text/css")


@app.get("/static/app.js")
def script():
    return FileResponse(BASE_DIR / "app.js", media_type="application/javascript")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "embedding_model": EMBEDDING_MODEL_NAME,
        "deepseek_configured": bool(DEEPSEEK_API_KEY and DEEPSEEK_API_BASE_URL),
        "documents_count": len(get_documents_snapshot()),
    }


@app.get("/api/documents")
def get_documents():
    docs = get_documents_snapshot()
    return {"documents": [serialize_document(doc) for doc in docs]}


@app.post("/api/upload")
def upload_file(request: UploadRequest):
    file_name = request.file_name.strip()
    if not file_name:
        raise HTTPException(status_code=400, detail="文件名不能为空。")

    try:
        file_bytes = base64.b64decode(request.content_base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="文件内容无法解析，请重新上传。") from exc

    try:
        text, file_type = extract_text_from_file(file_name, file_bytes)
        created_docs = add_uploaded_documents(file_name, file_type, text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"文件处理失败：{type(exc).__name__} {exc}") from exc

    return {
        "message": f"文件 {file_name} 上传成功，已新增 {len(created_docs)} 条知识片段。",
        "file_name": file_name,
        "file_type": file_type,
        "documents_added": len(created_docs),
        "documents": [serialize_document(doc) for doc in created_docs],
    }


@app.post("/api/ask")
def ask(request: AskRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空。")

    try:
        retrieved_docs = retrieve_documents(question)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"本地检索失败：{type(exc).__name__} {exc}") from exc

    context_text = build_context_text(retrieved_docs)
    answer_source = "fallback"
    llm_error = None

    try:
        answer = call_deepseek(question, context_text)
        answer_source = "deepseek"
    except Exception as exc:
        llm_error = f"{type(exc).__name__}: {exc}"
        answer = build_fallback_answer(question, retrieved_docs)

    return {
        "question": question,
        "answer": answer,
        "answer_source": answer_source,
        "llm_error": llm_error,
        "retrieval_queries": build_retrieval_queries(question),
        "retrieved_documents": [serialize_document(doc) for doc in retrieved_docs],
    }


if __name__ == "__main__":
    uvicorn.run("Embedding_model:app", host="127.0.0.1", port=8000, reload=True)
