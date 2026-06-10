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
        self._bm25 = None
        self._bm25_docs = []
        self._bm25_ids = []
        self._bm25_meta = []

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

    def _get_bm25(self):
        """懒加载 BM25 索引（从 ChromaDB 全量拉取文本构建）。"""
        if self._bm25 is not None:
            return self._bm25
        try:
            import jieba
            from rank_bm25 import BM25Okapi
            all_docs = self.collection.get(include=["documents", "metadatas"])  # ids 默认返回
            texts = all_docs.get("documents") or []
            if not texts:
                return None
            # 中文分词 + 英文空格切分
            tokenized = [list(jieba.cut(t)) for t in texts]
            self._bm25 = BM25Okapi(tokenized)
            self._bm25_docs = texts
            self._bm25_ids = all_docs.get("ids") or []
            self._bm25_meta = all_docs.get("metadatas") or []
            logger.info(f"BM25 索引构建完成，共 {len(texts)} 个文档")
        except Exception as e:
            logger.warning(f"BM25 索引构建失败: {e}")
            return None
        return self._bm25

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
        self._bm25 = None  # 新文档入库，BM25 索引失效，下次懒加载重建
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

    def hybrid_search(
        self,
        query: str,
        top_k: int = 5,
        rrf_k: int = 60,
        rerank: bool = True,
        rerank_top_k: int = 3,
    ) -> list[RetrievedChunk]:
        """混合检索：BM25 + 向量检索，RRF 融合后可选 Reranker 精排。"""
        import jieba

        # 1. 向量检索
        vector_chunks = self.search(query, top_k=top_k, rerank=False)

        # 2. BM25 检索
        bm25 = self._get_bm25()
        bm25_chunks = []
        if bm25 is not None:
            try:
                tokens = list(jieba.cut(query))
                scores = bm25.get_scores(tokens)
                top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
                for rank, idx in enumerate(top_indices):
                    if scores[idx] > 0:
                        bm25_chunks.append(RetrievedChunk(
                            text=self._bm25_docs[idx],
                            source=self._bm25_meta[idx].get("source", "unknown") if self._bm25_meta else "unknown",
                            score=scores[idx],
                            metadata=self._bm25_meta[idx] if self._bm25_meta else {},
                        ))
            except Exception as e:
                logger.warning(f"BM25 检索失败，降级到纯向量检索: {e}")

        if not bm25_chunks:
            return self.search(query, top_k=top_k, rerank=rerank, rerank_top_k=rerank_top_k)

        # 3. RRF 融合
        scores_map: dict[str, float] = {}
        text_map: dict[str, RetrievedChunk] = {}

        for rank, chunk in enumerate(vector_chunks):
            key = chunk.text[:100]
            scores_map[key] = scores_map.get(key, 0) + 1 / (rrf_k + rank + 1)
            text_map[key] = chunk

        for rank, chunk in enumerate(bm25_chunks):
            key = chunk.text[:100]
            scores_map[key] = scores_map.get(key, 0) + 1 / (rrf_k + rank + 1)
            text_map[key] = chunk

        merged = sorted(
            [text_map[k] for k in scores_map],
            key=lambda c: scores_map[c.text[:100]],
            reverse=True,
        )[:top_k]

        for chunk in merged:
            chunk.score = scores_map[chunk.text[:100]]

        if not rerank:
            return merged

        # 4. Reranker 精排
        reranker = self._get_reranker()
        if reranker is None:
            return merged
        try:
            pairs = [[query, c.text] for c in merged]
            rerank_scores = reranker.predict(pairs)
            for chunk, s in zip(merged, rerank_scores):
                chunk.score = float(s)
            merged.sort(key=lambda c: c.score, reverse=True)
            return merged[:rerank_top_k]
        except Exception as e:
            logger.warning(f"Reranker 精排失败: {e}")
            return merged

    def get_doc_count(self) -> int:
        return self.collection.count()

    def delete_doc(self, doc_id: str) -> None:
        """删除指定 doc_id 的所有 chunk。"""
        results = self.collection.get(where={"doc_id": doc_id})
        if results["ids"]:
            self.collection.delete(ids=results["ids"])
            logger.info(f"删除 doc_id={doc_id} 的 {len(results['ids'])} 个 chunk")
