import logging
from typing import Optional

from chromadb import Documents, EmbeddingFunction, Embeddings

logger = logging.getLogger(__name__)

_EMBEDDING_FN_CACHE: Optional["BGEZhEmbedding"] = None


class BGEZhEmbedding(EmbeddingFunction):
    """Chinese-optimized embedding using BAAI/bge-small-zh-v1.5 (512-dim)."""

    def __init__(self):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
        self._dim = self._model.get_sentence_embedding_dimension()

    def __call__(self, input: Documents) -> Embeddings:
        embeddings = self._model.encode(
            input,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    @property
    def dimension(self) -> int:
        return self._dim


BGE_SIGNATURE = {
    "model": "BAAI/bge-small-zh-v1.5",
    "dimension": 512,
    "description": "BGE-small Chinese, MTEB-Chinese top-tier",
}

ONNX_SIGNATURE = {
    "model": "ONNXMiniLM_L6_V2",
    "dimension": 384,
    "description": "all-MiniLM-L6-v2 ONNX export, English-optimized",
}


def get_embedding_fn():
    global _EMBEDDING_FN_CACHE
    if _EMBEDDING_FN_CACHE is None:
        try:
            _EMBEDDING_FN_CACHE = BGEZhEmbedding()
            logger.info(f"BGE-Zh embedding ready, dim={_EMBEDDING_FN_CACHE.dimension}")
        except Exception:
            logger.warning("BGE failed to load, falling back to ONNX", exc_info=True)
            from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

            _EMBEDDING_FN_CACHE = ONNXMiniLM_L6_V2()
            logger.info("ONNX embedding ready")
    return _EMBEDDING_FN_CACHE


def get_embedding_dim() -> int:
    fn = get_embedding_fn()
    return getattr(fn, "dimension", 384)


def get_embedding_signature() -> dict:
    """返回当前实际加载的 embedding 模型的签名（非写死常量）。"""
    fn = get_embedding_fn()
    if isinstance(fn, BGEZhEmbedding):
        return dict(BGE_SIGNATURE)
    return dict(ONNX_SIGNATURE)
