import logging
import os
from functools import lru_cache
from typing import Literal

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from .state import AgentState
from .tools import TOOLS, rag_search, web_search

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个视频技术专家助手，专门回答关于 HLS/DASH 协议、H.264/H.265 编码、视频分发、CDN、码率控制等视频技术问题。

回答规范：
1. 优先基于检索到的知识库内容回答，明确引用来源
2. 如果知识库没有相关内容，基于你的专业知识回答
3. 技术术语保持英文（HLS、GOP、bitrate 等），解释用中文
4. 回答简洁准确，不要冗余"""

ROUTER_PROMPT = """判断以下问题是否需要检索视频技术知识库。

如果问题涉及：HLS/DASH/RTMP 协议、H.264/H.265/AV1 编码、视频容器格式、CDN 分发、码率控制、GOP、关键帧、转码、ABR 等视频技术概念，回答 "rag"。
如果问题需要最新新闻/实时数据，回答 "web"。
如果是简单问候或无需检索，回答 "direct"。

只回答 rag/web/direct 三个词之一，不要其他内容。"""


def router_node(state: AgentState) -> AgentState:
    """判断 query 路由到哪个 Tool 或直接生成。"""
    llm = _get_llm()
    query = state["query"]
    response = llm.invoke([
        SystemMessage(content=ROUTER_PROMPT),
        HumanMessage(content=query),
    ])
    route = response.content.strip().lower()
    if route not in ("rag", "web", "direct"):
        route = "rag"  # 降级到 RAG
    logger.info(f"路由决策: {route}，query={query[:50]}")
    return {**state, "route": route}


def tool_node_func(state: AgentState) -> AgentState:
    """执行选中的 Tool，结果存入 retrieved_chunks。"""
    route = state.get("route", "rag")
    query = state["query"]

    if route == "rag":
        result = rag_search.invoke(query)
    elif route == "web":
        result = web_search.invoke(query)
    else:
        return {**state, "retrieved_chunks": [], "sources": []}

    return {**state, "retrieved_chunks": [result], "sources": [route]}


def generate_node(state: AgentState) -> AgentState:
    """调用 Claude API 生成最终回答。"""
    llm = _get_llm()
    query = state["query"]
    chunks = state.get("retrieved_chunks", [])

    if chunks and chunks[0]:
        context = "\n\n".join(chunks)
        user_content = f"参考以下资料回答问题：\n\n{context}\n\n问题：{query}"
    else:
        user_content = query

    messages = list(state.get("messages", []))
    messages.append(HumanMessage(content=user_content))

    try:
        response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT)] + messages)
        answer = response.content
    except Exception as e:
        logger.error(f"LLM 生成失败: {e}")
        answer = f"生成回答时出错：{str(e)}"

    return {**state, "answer": answer, "messages": messages + [response]}


def route_condition(state: AgentState) -> Literal["tool", "generate"]:
    """条件边：direct 路由跳过 tool_node 直接生成。"""
    return "generate" if state.get("route") == "direct" else "tool"


def build_graph():
    """构建并编译 LangGraph 状态机。"""
    graph = StateGraph(AgentState)
    graph.add_node("router", router_node)
    graph.add_node("tool", tool_node_func)
    graph.add_node("generate", generate_node)

    graph.add_edge(START, "router")
    graph.add_conditional_edges("router", route_condition, {"tool": "tool", "generate": "generate"})
    graph.add_edge("tool", "generate")
    graph.add_edge("generate", END)

    return graph.compile()


_graph_instance = None

def get_graph():
    """获取编译好的 graph 单例。"""
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = build_graph()
    return _graph_instance


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model="glm-4-flash",
        api_key=os.getenv("ZHIPU_API_KEY", ""),
        base_url="https://open.bigmodel.cn/api/paas/v4/",
        max_tokens=2048,
    )
