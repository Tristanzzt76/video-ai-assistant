import logging
import os
import uuid
from pathlib import Path
import aiofiles
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

from src.models.schemas import (
    UploadResponse, ChatRequest, ChatResponse,
    DocsListResponse, DocInfo, HealthResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# 简单内存存储文档元信息（生产环境应用数据库）
_docs_registry: dict[str, dict] = {}


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查接口。"""
    from src.rag.embedder import get_embedder
    from src.rag.retriever import ChromaRetriever
    from src.config import get_settings

    embedder = get_embedder()
    settings = get_settings()

    try:
        retriever = ChromaRetriever(settings.chroma_path)
        count = retriever.get_doc_count()
    except Exception:
        count = -1

    return HealthResponse(
        status="ok",
        vector_store_count=count,
        embedding_model_loaded=embedder._model is not None,
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """上传 PDF 或 Markdown 文档，解析并写入向量数据库。"""
    from src.config import get_settings
    from src.rag.loader import DocumentLoader
    from src.rag.retriever import ChromaRetriever

    allowed_types = {".pdf", ".md", ".txt"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed_types:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {suffix}，支持 {allowed_types}")

    settings = get_settings()
    doc_id = str(uuid.uuid4())[:8]

    # 保存文件到本地
    save_path = Path(settings.docs_path) / f"{doc_id}{suffix}"
    save_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        async with aiofiles.open(save_path, "wb") as f:
            content = await file.read()
            await f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")

    # 解析并写入向量库
    try:
        loader = DocumentLoader()
        docs = loader.load_file(str(save_path))
        retriever = ChromaRetriever(settings.chroma_path)
        chunk_count = retriever.add_documents(docs, doc_id)
    except Exception as e:
        logger.error(f"文档处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"文档处理失败: {str(e)}")

    _docs_registry[doc_id] = {"filename": file.filename, "chunk_count": chunk_count}

    return UploadResponse(
        doc_id=doc_id,
        filename=file.filename or "",
        chunk_count=chunk_count,
        message=f"成功处理 {chunk_count} 个 chunk",
    )


@router.post("/chat")
async def chat(request: ChatRequest):
    """问答接口，stream=True 时返回 SSE 流，stream=False 时返回 JSON。"""
    if request.stream:
        from src.agent.graph import stream_graph
        import json

        async def event_stream():
            try:
                async for chunk in stream_graph(request.query, request.session_id):
                    yield chunk
            except Exception as e:
                logger.error(f"流式生成失败: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # 原有同步逻辑保持不变
    from src.agent.graph import get_graph

    try:
        graph = get_graph()
        result = graph.invoke({
            "query": request.query,
            "session_id": request.session_id,
            "messages": [],
            "retrieved_chunks": [],
            "sources": [],
            "route": "rag",
            "answer": "",
        })
    except Exception as e:
        logger.error(f"Agent 处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")

    return ChatResponse(
        answer=result.get("answer", ""),
        sources=result.get("sources", []),
        route=result.get("route", "rag"),
        session_id=request.session_id,
    )


@router.get("/docs-list", response_model=DocsListResponse)
async def list_docs():
    """返回已上传的文档列表。"""
    docs = [
        DocInfo(doc_id=doc_id, filename=info["filename"], chunk_count=info["chunk_count"])
        for doc_id, info in _docs_registry.items()
    ]
    return DocsListResponse(docs=docs, total=len(docs))
