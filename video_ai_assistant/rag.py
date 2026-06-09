from __future__ import annotations

from dataclasses import dataclass, field
import heapq
import re
from typing import Dict, Iterable, List


@dataclass
class VideoChunk:
    video_id: str
    timestamp: str
    text: str
    metadata: Dict[str, str] = field(default_factory=dict)


class VideoKnowledgeBase:
    def __init__(self) -> None:
        self._chunks: List[VideoChunk] = []

    def add_chunk(self, chunk: VideoChunk) -> None:
        self._chunks.append(chunk)

    def add_chunks(self, chunks: Iterable[VideoChunk]) -> None:
        self._chunks.extend(chunks)

    def retrieve(self, query: str, top_k: int = 3) -> List[VideoChunk]:
        query_tokens = set(re.findall(r"\w+", query.lower()))

        def score(chunk: VideoChunk) -> float:
            text = chunk.text.lower()
            tokens = set(re.findall(r"\w+", text))
            overlap = len(query_tokens & tokens)
            substring_bonus = 1 if query.lower() in text else 0
            return overlap + substring_bonus

        scored = ((score(chunk), chunk) for chunk in self._chunks)
        ranked = heapq.nlargest(top_k, scored, key=lambda item: item[0])
        return [chunk for chunk_score, chunk in ranked if chunk_score > 0]
