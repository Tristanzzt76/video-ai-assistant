import logging
from langchain_core.tools import tool
from typing import Optional

logger = logging.getLogger(__name__)

# 全局检索器引用（在 app.py startup 时注入）
_retriever = None

def set_retriever(retriever) -> None:
    """注入 ChromaRetriever 实例（在 FastAPI startup 时调用）。"""
    global _retriever
    _retriever = retriever

@tool
def rag_search(query: str) -> str:
    """在视频技术知识库中检索相关内容。适用于 HLS/DASH/H.264/视频编码等专业问题。"""
    if _retriever is None:
        return "知识库未初始化"
    try:
        chunks = _retriever.search(query, top_k=5, rerank=True, rerank_top_k=3)
        if not chunks:
            return "知识库中未找到相关内容"
        return "\n\n---\n\n".join(
            f"[来源: {c.source}（相关度: {c.score:.2f}）]\n{c.text}"
            for c in chunks
        )
    except Exception as e:
        logger.error(f"RAG 检索失败: {e}")
        return f"检索出错: {str(e)}"

@tool
def web_search(query: str) -> str:
    """在互联网上搜索最新信息。适用于知识库没有覆盖的问题或需要最新资讯。"""
    import os
    # 优先 Tavily（如果配置了）
    tavily_key = os.getenv("TAVILY_API_KEY", "")
    if tavily_key and not tavily_key.startswith("tvly-your"):
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=tavily_key)
            response = client.search(query, max_results=3)
            results = response.get("results", [])
            if results:
                return "\n\n---\n\n".join(
                    f"[{r.get('title','')}]\n{r.get('content','')}"
                    for r in results
                )
        except Exception as e:
            logger.warning(f"Tavily 失败，降级到 DuckDuckGo: {e}")

    # 降级到 DuckDuckGo（免费）
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        if not results:
            return "未找到相关网页内容"
        return "\n\n---\n\n".join(
            f"[{r.get('title','')}]\n{r.get('body','')}"
            for r in results
        )
    except Exception as e:
        logger.error(f"Web 搜索失败: {e}")
        return f"Web 搜索出错: {str(e)}"

TOOLS = [rag_search, web_search]
