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


class ZhipuAPIEmbedder:
    """Zhipu embedding-3 API embedder，部署时无需本地模型。"""

    _instance = None
    _client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self) -> None:
        if self._client is not None:
            return
        try:
            from openai import OpenAI
            import os
            self._client = OpenAI(
                api_key=os.getenv("ZHIPU_API_KEY", ""),
                base_url="https://open.bigmodel.cn/api/paas/v4/",
            )
            logger.info("Zhipu Embedding API 初始化完成（部署模式）")
        except Exception as e:
            logger.error(f"Zhipu Embedding 初始化失败: {e}")
            raise

    def encode(self, texts, batch_size: int = 32):
        import numpy as np
        if isinstance(texts, str):
            texts = [texts]
        if self._client is None:
            raise RuntimeError("Embedder 未加载，请先调用 load()")
        # 分批处理，避免超过 API 限制
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            response = self._client.embeddings.create(
                model="embedding-3",
                input=batch,
                dimensions=1024,  # 与 BGE-M3 相同维度
            )
            all_embeddings.extend([d.embedding for d in response.data])
        return np.array(all_embeddings, dtype=np.float32)

    def encode_query(self, query: str):
        return self.encode(query)[0]


@lru_cache(maxsize=1)
def get_embedder():
    import os
    if os.getenv("EMBEDDING_MODEL", "local").lower() == "api":
        return ZhipuAPIEmbedder()
    return BGEEmbedder()
