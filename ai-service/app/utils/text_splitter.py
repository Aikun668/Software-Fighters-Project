from langchain_classic.text_splitter import RecursiveCharacterTextSplitter


# Module classification for knowledge docs
_FILENAME_TO_MODULE: dict[str, str] = {}


def _build_module_map():
    """Lazily build filename stem → module name mapping."""
    if _FILENAME_TO_MODULE:
        return
    _FILENAME_TO_MODULE.update({
        "01-ai-overview": "人工智能概述",
        "02-machine-learning": "机器学习",
        "03-deep-learning": "深度学习",
        "04-transformer": "Transformer架构",
        "05-nlp-llm": "自然语言处理与大语言模型",
        "06-backprop-derivation": "反向传播详解",
        "07-overfitting-regularization": "过拟合与正则化",
        "08-self-attention-detail": "自注意力机制详解",
        "09-gradient-descent-variants": "梯度下降变体",
        "10-exercises-with-answers": "练习题与解析",
    })


def classify_module(filename: str) -> str:
    """Map filename to a module category tag."""
    _build_module_map()
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return _FILENAME_TO_MODULE.get(stem, "通用")


def split_text(
    text: str,
    source: str = "",
    chunk_size: int = 640,
    chunk_overlap: int = 80,
) -> list[dict]:
    separators = ["\n---\n", "\n## ", "\n# ", "\n\n", "\n", "。", "！", "？", "；", " ", ""]
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=separators,
    )
    chunks = splitter.split_text(text)
    module = classify_module(source)
    return [
        {
            "content": chunk,
            "metadata": {
                "source": source,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "module": module,
            },
        }
        for i, chunk in enumerate(chunks)
    ]
