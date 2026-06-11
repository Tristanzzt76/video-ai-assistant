import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import get_settings
from src.api.routes import router

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时预热模型，关闭时清理资源。"""
    settings = get_settings()

    # 确保数据目录存在
    Path(settings.docs_path).mkdir(parents=True, exist_ok=True)
    Path(settings.chroma_path).mkdir(parents=True, exist_ok=True)

    # 预加载 BGE-M3（首次需下载 ~550MB，失败时降级启动）
    from src.rag.embedder import get_embedder
    embedder = get_embedder()
    try:
        embedder.load()
    except Exception as e:
        logger.warning(f"BGE-M3 加载失败（服务仍可启动，但 /upload /chat 不可用）: {e}")

    # 注入 retriever 到 tools
    from src.rag.retriever import ChromaRetriever
    from src.agent.tools import set_retriever
    retriever = ChromaRetriever(settings.chroma_path)
    set_retriever(retriever)

    # 如果 ChromaDB 为空，自动加载内置文档（适用于首次部署）
    if retriever.get_doc_count() == 0:
        logger.info("知识库为空，自动加载内置文档...")
        from src.rag.loader import DocumentLoader
        loader = DocumentLoader()
        docs_loaded = 0
        for doc_file in Path(settings.docs_path).glob("*.md"):
            try:
                docs = loader.load_file(str(doc_file))
                for doc in docs:
                    doc.metadata["original_filename"] = doc_file.name
                retriever.add_documents(docs, doc_file.stem[:8])
                docs_loaded += len(docs)
            except Exception as e:
                logger.warning(f"自动加载 {doc_file.name} 失败: {e}")
        if docs_loaded > 0:
            logger.info(f"自动加载完成，共 {retriever.get_doc_count()} 个 chunk")

    logger.info("服务启动完成，访问 http://localhost:8000/docs 查看 API 文档")
    yield
    logger.info("服务关闭")


app = FastAPI(
    title="视频技术 AI 问答助手",
    description="RAG + LangGraph Agent，专注视频技术领域问答",
    version="0.1.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
