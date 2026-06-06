import os
import sys
import logging
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.knowledge_base import get_kb
from app.utils.text_splitter import split_text, classify_module

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


def import_documents(docs_dir: str = "knowledge_docs"):
    kb = get_kb()
    docs_path = Path(docs_dir)

    if not docs_path.exists():
        logger.warning(f"Directory not found: {docs_path}")
        return

    if not kb.is_empty():
        logger.warning(
            "Collection is not empty. Delete chroma_data/ first to force re-import, "
            "or use upsert mode (existing IDs will be updated)."
        )

    total_chunks = 0
    total_files = 0
    module_counts: dict[str, int] = {}

    for ext in ["*.md", "*.txt"]:
        files = sorted(docs_path.rglob(ext))
        for file_path in files:
            total_files += 1
            try:
                text = file_path.read_text(encoding="utf-8")
                if not text.strip():
                    logger.info(f"  Skip empty: {file_path.name}")
                    continue

                chunks = split_text(text, source=file_path.name)
                if not chunks:
                    continue

                texts = [c["content"] for c in chunks]
                metadatas = [c["metadata"] for c in chunks]
                ids = [f"{file_path.stem}_{i:03d}" for i in range(len(chunks))]

                kb.add_documents(texts, metadatas, ids)
                total_chunks += len(chunks)

                module = classify_module(file_path.name)
                module_counts[module] = module_counts.get(module, 0) + len(chunks)

                logger.info(
                    f"  [{module}] {file_path.name}: {len(chunks)} chunks"
                )
            except Exception as e:
                logger.warning(f"  FAILED {file_path.name}: {e}")

    logger.info(f"--- Import Summary ---")
    logger.info(f"  Files: {total_files}, Chunks: {total_chunks}")
    for mod, count in sorted(module_counts.items(), key=lambda x: -x[1]):
        logger.info(f"  {mod}: {count} chunks")
    logger.info(f"  Total vectors in DB: {kb.collection.count()}")


if __name__ == "__main__":
    docs_dir = sys.argv[1] if len(sys.argv) > 1 else "knowledge_docs"
    import_documents(docs_dir)
