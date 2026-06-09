from typing import Annotated, Literal
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    """LangGraph 状态：贯穿整个 Agent 执行流的数据容器。"""
    messages: Annotated[list[BaseMessage], add_messages]
    query: str
    retrieved_chunks: list[str]
    sources: list[str]
    route: Literal["rag", "web", "direct"]
    answer: str
    session_id: str
