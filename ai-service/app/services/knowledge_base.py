import os
import json
import logging
from pathlib import Path
from typing import Optional

import chromadb

from app.utils.embeddings import get_embedding_fn, get_embedding_dim, get_embedding_signature

logger = logging.getLogger(__name__)

SIGNATURE_FILE = "embedding_signature.json"


class KnowledgeBase:
    def __init__(
        self,
        persist_path: str = "./chroma_data",
        collection_name: str = "ai_intro",
    ):
        self.persist_path = persist_path
        self.collection_name = collection_name
        self.client = chromadb.PersistentClient(path=persist_path)

        self.embedding_fn = get_embedding_fn()
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
        self._verify_embedding_signature()
        logger.info(f"KnowledgeBase ready: {persist_path}/{collection_name} ({get_embedding_dim()}d)")

    def _signature_path(self) -> Path:
        return Path(self.persist_path) / SIGNATURE_FILE

    def _verify_embedding_signature(self) -> None:
        """Warn if the stored embedding signature differs from current (model changed → re-index needed)."""
        sig_path = self._signature_path()
        if sig_path.exists():
            try:
                stored = json.loads(sig_path.read_text(encoding="utf-8"))
                current = get_embedding_signature()
                if stored.get("model") != current["model"]:
                    logger.warning(
                        f"Embedding model changed! Stored: {stored['model']}, "
                        f"Current: {current['model']}. "
                        "Run import_knowledge.py to re-index."
                    )
            except Exception:
                pass

    def _write_embedding_signature(self) -> None:
        self._signature_path().parent.mkdir(parents=True, exist_ok=True)
        self._signature_path().write_text(
            json.dumps(get_embedding_signature(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def add_documents(
        self, texts: list[str], metadatas: list[dict] | None = None, ids: list[str] | None = None
    ) -> None:
        if not texts:
            return
        if metadatas is None:
            metadatas = [{} for _ in texts]
        if ids is None:
            ids = [f"doc_{i}" for i in range(len(texts))]
        try:
            self.collection.upsert(documents=texts, metadatas=metadatas, ids=ids)
            self._write_embedding_signature()
            logger.info(f"Added {len(texts)} documents to {self.collection_name}")
        except Exception as e:
            logger.error(f"Failed to add documents: {e}")
            raise

    def search(
        self, query: str, top_k: int = 5, module_filter: str | None = None
    ) -> list[dict]:
        where_filter = {"module": module_filter} if module_filter else None
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where_filter,
        )
        docs = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                docs.append({
                    "content": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "score": results["distances"][0][i] if results["distances"] else 0,
                })
        if not docs:
            docs = self._keyword_fallback(query, top_k)
        return docs

    def search_multi_module(
        self, query: str, top_k: int = 5, modules: list[str] | None = None
    ) -> list[dict]:
        """Search across specific modules and merge results."""
        if not modules:
            return self.search(query, top_k)

        all_docs: list[dict] = []
        per_module = max(top_k // len(modules), 2)
        for mod in modules:
            docs = self.search(query, per_module, module_filter=mod)
            all_docs.extend(docs)

        seen = set()
        deduped = []
        for doc in all_docs:
            key = doc["content"][:100]
            if key not in seen:
                seen.add(key)
                deduped.append(doc)
        return deduped[:top_k]

    def _keyword_fallback(self, query: str, top_k: int) -> list[dict]:
        try:
            all_docs = self.collection.get()
            if not all_docs or not all_docs["documents"]:
                return []
            
            query_chars = set(query)
            scored = []
            for i, doc in enumerate(all_docs["documents"]):
                if not doc:
                    continue
                score = sum(1 for c in query_chars if c in doc)
                scored.append((score, i, doc))
            
            scored.sort(reverse=True)
            docs = []
            for score, i, doc in scored[:top_k]:
                meta = all_docs["metadatas"][i] if all_docs["metadatas"] else {}
                docs.append({"content": doc, "metadata": meta, "score": score})
            return docs
        except Exception as e:
            logger.warning(f"Keyword fallback failed: {e}")
            return []

    def format_context(self, query: str, top_k: int = 5) -> str:
        docs = self.search(query, top_k)
        if not docs:
            return ""
        parts = ["【参考知识库内容】"]
        for i, doc in enumerate(docs, 1):
            parts.append(f"[{i}] {doc['content']}")
        return "\n".join(parts)

    def is_empty(self) -> bool:
        try:
            return self.collection.count() == 0
        except Exception:
            return True


_kb_instance: Optional[KnowledgeBase] = None


def get_kb() -> KnowledgeBase:
    global _kb_instance
    if _kb_instance is None:
        persist = os.getenv("CHROMA_PERSIST_PATH", "./chroma_data")
        coll = os.getenv("CHROMA_COLLECTION", "ai_intro")
        _kb_instance = KnowledgeBase(persist_path=persist, collection_name=coll)
    return _kb_instance
