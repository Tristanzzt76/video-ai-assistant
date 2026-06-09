import logging
import numpy as np
from functools import lru_cache
from typing import Union

logger = logging.getLogger(__name__)

class BGEEmbedder:
    """BGE-M3 本地 Embedding，单例模式，应用启动时预加载。"""

    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, model_name: str = "BAAI/bge-m3") -> None:
        """加载模型（应在 FastAPI startup 事件中调用）。"""
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"加载 Embedding 模型: {model_name}（首次加载约 10-30s）")
            self._model = SentenceTransformer(model_name)
            logger.info("Embedding 模型加载完成")
        except Exception as e:
            logger.error(f"加载 Embedding 模型失败: {e}")
            raise

    def encode(self, texts: Union[str, list[str]], batch_size: int = 32) -> np.ndarray:
        """将文本编码为向量。单个字符串或字符串列表均可。"""
        if self._model is None:
            raise RuntimeError("模型未加载，请先调用 load()")
        if isinstance(texts, str):
            texts = [texts]
        return self._model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,  # 归一化，适合余弦相似度
        )

    def encode_query(self, query: str) -> np.ndarray:
        """编码单个 query，返回 1D 向量。"""
        return self.encode(query)[0]


@lru_cache(maxsize=1)
def get_embedder() -> BGEEmbedder:
    return BGEEmbedder()
