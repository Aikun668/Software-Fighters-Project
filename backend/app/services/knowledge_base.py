"""
ChromaDB 向量知识库检索

基于「人工智能导论」课程知识库：
  - 文档加载与分片
  - 向量化存储（阿里 embedding 模型）
  - 语义检索
"""

import os
import logging
from typing import Optional

import chromadb

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """ChromaDB 向量知识库管理器"""

    def __init__(
        self,
        persist_path: str = "./chroma_data",
        collection_name: str = "ai_intro",
    ):
        self.persist_path = persist_path
        self.collection_name = collection_name
        self.client = chromadb.PersistentClient(path=persist_path)
        self.collection = self.client.get_or_create_collection(
            name=collection_name
        )
        logger.info(
            f"KnowledgeBase ready: {persist_path}/{collection_name}"
        )

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """语义检索，返回 top_k 个最相关文档片段"""
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
        )
        docs = []
        if results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                docs.append({
                    "content": doc,
                    "metadata": (
                        results["metadatas"][0][i]
                        if results["metadatas"] else {}
                    ),
                    "score": (
                        results["distances"][0][i]
                        if results["distances"] else 0
                    ),
                })
        return docs

    def format_context(self, query: str, top_k: int = 5) -> str:
        """检索并格式化为 prompt 可用的上下文文本"""
        docs = self.search(query, top_k)
        if not docs:
            return ""
        parts = ["【参考知识库内容】"]
        for i, doc in enumerate(docs, 1):
            parts.append(f"[{i}] {doc['content']}")
        return "\n".join(parts)


_kb_instance: Optional[KnowledgeBase] = None


def get_kb() -> KnowledgeBase:
    """获取全局知识库单例"""
    global _kb_instance
    if _kb_instance is None:
        persist = os.getenv("CHROMA_PERSIST_PATH", "./chroma_data")
        coll = os.getenv("CHROMA_COLLECTION", "ai_intro")
        _kb_instance = KnowledgeBase(
            persist_path=persist, collection_name=coll
        )
    return _kb_instance
