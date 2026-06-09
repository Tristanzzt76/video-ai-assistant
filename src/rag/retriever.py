import logging
from dataclasses import dataclass
from typing import Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from llama_index.core.schema import Document

from .embedder import get_embedder

logger = logging.getLogger(__name__)

@dataclass
class RetrievedChunk:
    text: str
    source: str
    score: float
    metadata: dict

class ChromaRetriever:
    """ChromaDB 向量检索 + BGE-Reranker 精排。"""

    def __init__(self, chroma_path: str, collection_name: str = "video_tech_docs"):
        self.client = chromadb.PersistentClient(
            path=chroma_path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._reranker = None

    def _get_reranker(self):
        """懒加载 BGE-Reranker（用 sentence-transformers CrossEncoder，兼容 transformers 5.x）。"""
        if self._reranker is None:
            try:
                from sentence_transformers import CrossEncoder
                self._reranker = CrossEncoder("BAAI/bge-reranker-base")
                logger.info("BGE-Reranker 加载完成（CrossEncoder）")
            except Exception as e:
                logger.warning(f"BGE-Reranker 加载失败，跳过精排: {e}")
        return self._reranker

    def add_documents(self, documents: list[Document], doc_id: str) -> int:
        """将文档 chunk 写入 ChromaDB。返回写入的 chunk 数量。"""
        if not documents:
            return 0
        embedder = get_embedder()
        texts = [doc.text for doc in documents]
        embeddings = embedder.encode(texts).tolist()
        ids = [f"{doc_id}_chunk_{i}" for i in range(len(documents))]
        metadatas = [{**doc.metadata, "doc_id": doc_id} for doc in documents]
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        logger.info(f"写入 {len(documents)} 个 chunk，doc_id={doc_id}")
        return len(documents)

    def search(
        self,
        query: str,
        top_k: int = 5,
        rerank: bool = True,
        rerank_top_k: int = 3,
    ) -> list[RetrievedChunk]:
        """检索相关 chunk，可选 BGE-Reranker 精排。"""
        embedder = get_embedder()
        query_vec = embedder.encode_query(query).tolist()

        results = self.collection.query(
            query_embeddings=[query_vec],
            n_results=min(top_k, self.collection.count() or 1),
            include=["documents", "metadatas", "distances"],
        )

        if not results["documents"] or not results["documents"][0]:
            return []

        chunks = [
            RetrievedChunk(
                text=text,
                source=meta.get("source", "unknown"),
                score=1 - dist,  # cosine distance → similarity
                metadata=meta,
            )
            for text, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ]

        if not rerank:
            return chunks

        reranker = self._get_reranker()
        if reranker is None:
            return chunks

        try:
            pairs = [[query, c.text] for c in chunks]
            scores = reranker.predict(pairs)  # CrossEncoder.predict，返回 raw logit scores
            for chunk, score in zip(chunks, scores):
                chunk.score = float(score)
            chunks.sort(key=lambda c: c.score, reverse=True)
            return chunks[:rerank_top_k]
        except Exception as e:
            logger.warning(f"Reranker 精排失败，返回原始结果: {e}")
            return chunks

    def get_doc_count(self) -> int:
        return self.collection.count()

    def delete_doc(self, doc_id: str) -> None:
        """删除指定 doc_id 的所有 chunk。"""
        results = self.collection.get(where={"doc_id": doc_id})
        if results["ids"]:
            self.collection.delete(ids=results["ids"])
            logger.info(f"删除 doc_id={doc_id} 的 {len(results['ids'])} 个 chunk")
