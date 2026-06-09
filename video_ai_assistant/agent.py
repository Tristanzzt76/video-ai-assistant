from __future__ import annotations

from typing import Callable, Dict, List, Optional, TypedDict

from .rag import VideoChunk, VideoKnowledgeBase

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover
    END = START = StateGraph = None


class QAState(TypedDict):
    question: str
    top_k: int
    context: List[VideoChunk]
    answer: str


class QAResponse(TypedDict):
    question: str
    context: List[VideoChunk]
    answer: str


class VideoRAGLangGraphAgent:
    def __init__(
        self,
        knowledge_base: VideoKnowledgeBase,
        answer_generator: Optional[Callable[[str, List[VideoChunk]], str]] = None,
    ) -> None:
        self._kb = knowledge_base
        self._answer_generator = answer_generator or self._default_answer_generator
        self._graph = self._build_graph()

    def _build_graph(self):
        if StateGraph is None:
            return None

        graph = StateGraph(QAState)
        graph.add_node("retrieve_context", self._retrieve_context)
        graph.add_node("generate_answer", self._generate_answer)
        graph.add_edge(START, "retrieve_context")
        graph.add_edge("retrieve_context", "generate_answer")
        graph.add_edge("generate_answer", END)
        return graph.compile()

    def _retrieve_context(self, state: QAState) -> Dict[str, List[VideoChunk]]:
        return {"context": self._kb.retrieve(state["question"], top_k=state["top_k"])}

    def _generate_answer(self, state: QAState) -> Dict[str, str]:
        return {"answer": self._answer_generator(state["question"], state["context"])}

    def ask(self, question: str, top_k: int = 3) -> QAResponse:
        initial_state: QAState = {
            "question": question,
            "top_k": top_k,
            "context": [],
            "answer": "",
        }
        if self._graph is not None:
            final_state = self._graph.invoke(initial_state)
        else:
            final_state = {
                **initial_state,
                **self._retrieve_context(initial_state),
            }
            final_state.update(self._generate_answer(final_state))

        return {
            "question": final_state["question"],
            "context": final_state["context"],
            "answer": final_state["answer"],
        }

    @staticmethod
    def _default_answer_generator(question: str, context: List[VideoChunk]) -> str:
        if not context:
            return "I could not find relevant video context for this question."

        lines = [f"Question: {question}", "Answer (from retrieved video context):"]
        for chunk in context:
            lines.append(f"- {chunk.text} [source: {chunk.video_id}@{chunk.timestamp}]")
        return "\n".join(lines)
