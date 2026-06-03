import pytest

from app.utils.mermaid_parser import (
    extract_mermaid_blocks,
    split_text_and_mermaid,
    strip_mermaid_from_text,
    _is_valid_mermaid,
)


class TestExtractMermaidBlocks:
    def test_basic_flowchart(self):
        text = """Here's a diagram:

```mermaid
graph TD
    A[Start] --> B[End]
```

More text."""
        blocks = extract_mermaid_blocks(text)
        assert len(blocks) == 1
        assert "graph TD" in blocks[0].code
        assert "A[Start] --> B[End]" in blocks[0].code

    def test_multiple_blocks(self):
        text = """First diagram:
```mermaid
graph TD
    A --> B
```

Second diagram:
```mermaid
sequenceDiagram
    A->>B: hello
```"""
        blocks = extract_mermaid_blocks(text)
        assert len(blocks) == 2
        assert "graph TD" in blocks[0].code
        assert "sequenceDiagram" in blocks[1].code

    def test_no_blocks(self):
        text = "Just plain text without any mermaid."
        blocks = extract_mermaid_blocks(text)
        assert len(blocks) == 0

    def test_invalid_type(self):
        text = """```mermaid
unknown diagram type
    A --> B
```"""
        blocks = extract_mermaid_blocks(text)
        assert len(blocks) == 0

    def test_case_insensitive(self):
        text = """```MERMAID
graph TD
    A --> B
```"""
        blocks = extract_mermaid_blocks(text)
        assert len(blocks) == 1


class TestSplitTextAndMermaid:
    def test_basic(self):
        text = """Hello world.

```mermaid
graph TD
    A --> B
```

Goodbye."""
        parts = split_text_and_mermaid(text)
        assert len(parts) == 3
        assert parts[0]["type"] == "text"
        assert "Hello world." in parts[0]["content"]
        assert parts[1]["type"] == "mermaid"
        assert "graph TD" in parts[1]["code"]
        assert parts[2]["type"] == "text"
        assert "Goodbye." in parts[2]["content"]

    def test_no_mermaid(self):
        text = "Just plain text."
        parts = split_text_and_mermaid(text)
        assert len(parts) == 1
        assert parts[0]["type"] == "text"


class TestStripMermaid:
    def test_basic(self):
        text = """Hello.

```mermaid
graph TD
    A --> B
```

World."""
        result = strip_mermaid_from_text(text)
        assert "Hello." in result
        assert "World." in result
        assert "```mermaid" not in result
        assert "graph TD" not in result

    def test_no_mermaid(self):
        text = "Just plain text."
        assert strip_mermaid_from_text(text) == "Just plain text."


class TestIsValidMermaid:
    def test_valid_types(self):
        assert _is_valid_mermaid("graph TD\n    A --> B")
        assert _is_valid_mermaid("graph LR\n    A --> B")
        assert _is_valid_mermaid("sequenceDiagram\n    A->>B: hi")
        assert _is_valid_mermaid("classDiagram\n    class A")
        assert _is_valid_mermaid("flowchart TD\n    A --> B")

    def test_invalid_types(self):
        assert not _is_valid_mermaid("unknown\n    A --> B")
        assert not _is_valid_mermaid("just some text")
        assert not _is_valid_mermaid("")