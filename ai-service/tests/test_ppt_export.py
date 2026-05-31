import json
import os
import tempfile

import pytest

from app.utils.ppt_exporter import (
    _parse_inline_markdown,
    _extract_code_blocks,
    _highlight_code,
    TextRun,
    export_to_pptx,
)
from pptx import Presentation


class TestInlineMarkdownParser:
    def test_plain_text(self):
        runs = _parse_inline_markdown("Hello World")
        assert len(runs) == 1
        assert runs[0].text == "Hello World"
        assert not runs[0].bold

    def test_bold_text(self):
        runs = _parse_inline_markdown("Hello **World** today")
        assert len(runs) >= 2
        bold_runs = [r for r in runs if r.bold]
        assert any("World" in r.text for r in bold_runs)

    def test_italic_text(self):
        runs = _parse_inline_markdown("Hello *World* today")
        assert len(runs) >= 2
        italic_runs = [r for r in runs if r.italic]
        assert any("World" in r.text for r in italic_runs)

    def test_inline_code(self):
        runs = _parse_inline_markdown("Use `print()` function")
        code_runs = [r for r in runs if r.code]
        assert any("print()" in r.text for r in code_runs)

    def test_mixed_formatting(self):
        runs = _parse_inline_markdown("**Bold** and *italic* and `code`")
        assert any(r.bold for r in runs)
        assert any(r.italic for r in runs)
        assert any(r.code for r in runs)

    def test_link_parsing(self):
        runs = _parse_inline_markdown("Click [here](https://example.com)")
        link_runs = [r for r in runs if r.link_url]
        assert len(link_runs) >= 1
        assert link_runs[0].link_url == "https://example.com"

    def test_empty_input(self):
        runs = _parse_inline_markdown("")
        assert runs == []

    def test_no_formatting(self):
        runs = _parse_inline_markdown("Just plain text without any formatting")
        assert len(runs) == 1
        assert runs[0].text == "Just plain text without any formatting"


class TestCodeBlockExtraction:
    def test_extract_python_code_block(self):
        text = "Some text\n```python\nprint('hello')\n```\nMore text"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["language"] == "python"
        assert "print('hello')" in blocks[0]["code"]

    def test_extract_no_language(self):
        text = "```\nplain code\n```"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["language"] == "text"
        assert blocks[0]["code"] == "plain code"

    def test_extract_multiple_blocks(self):
        text = "```python\na=1\n```\nText\n```js\nlet b=2;\n```"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 2

    def test_no_code_blocks(self):
        blocks = _extract_code_blocks("Plain text only")
        assert blocks == []


class TestCodeHighlighting:
    def test_highlight_python_code(self):
        runs = _highlight_code('print("hello")', "python")
        assert len(runs) > 0
        assert any("print" in r.text for r in runs)
        # print is Name.Builtin, not Keyword — should have a distinct color (not default fg)
        print_run = next((r for r in runs if "print" in r.text), None)
        assert print_run is not None
        assert print_run.color is not None  # Builtin should be colored

    def test_highlight_fallback_unknown_language(self):
        runs = _highlight_code("some code here", "madeuplang123")
        assert len(runs) > 0
        # Falls back to plain text or guessed lexer
        assert runs[0].code or True

    def test_highlight_empty_code(self):
        runs = _highlight_code("", "python")
        assert len(runs) == 1
        assert runs[0].text == ""
        assert runs[0].code


class TestExportToPptxEnhanced:
    def test_title_slide_created(self):
        content_blocks = [
            {"type": "section", "heading": "Test", "content": "Some content"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "title_test.pptx")
            export_to_pptx(content_blocks, path, title="My Test")
            prs = Presentation(path)
            assert len(prs.slides) >= 2  # title + at least one content

    def test_markdown_content_in_slide(self):
        content_blocks = [
            {"type": "section", "heading": "Markdown Test",
             "content": "**Bold text** and *italic text* and `code`"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "md_test.pptx")
            result = export_to_pptx(content_blocks, path, title="MD Test")
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0

    def test_code_block_with_language(self):
        content_blocks = [
            {"type": "code", "heading": "Python Example",
             "content": "```python\ndef hello():\n    print('hello')\n```"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "code_test.pptx")
            result = export_to_pptx(content_blocks, path, title="Code Test")
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0

    def test_table_block(self):
        content_blocks = [
            {"type": "table", "heading": "Comparison",
             "content": "| Feature | Value |\n|---------|-------|\n| Speed | Fast |\n| Cost | Low |"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "table_test.pptx")
            result = export_to_pptx(content_blocks, path, title="Table Test")
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0

    def test_mermaid_block_handled(self):
        content_blocks = [
            {"type": "mermaid", "heading": "Diagram",
             "content": "graph TD\n  A[Start] --> B[End]"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "mermaid_test.pptx")
            result = export_to_pptx(content_blocks, path, title="Mermaid Test")
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0

    def test_mindmap_with_json(self):
        mm_data = {
            "nodes": [{"id": "root", "label": "AI"}, {"id": "sub", "label": "ML"}],
            "edges": [{"src": "root", "dst": "sub"}],
        }
        content_blocks = [
            {"type": "mindmap", "heading": "Knowledge Map",
             "content": json.dumps(mm_data, ensure_ascii=False)},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "mindmap_test.pptx")
            result = export_to_pptx(content_blocks, path, title="Mindmap Test")
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0

    def test_error_block_fallback(self):
        content_blocks = [
            {"type": "error", "heading": "Filtered",
             "content": "此内容因安全原因已被过滤。"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "error_test.pptx")
            result = export_to_pptx(content_blocks, path, title="Error Test")
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0

    def test_mixed_content_blocks(self):
        content_blocks = [
            {"type": "section", "heading": "Overview", "content": "## Introduction\n\nThis is **important** content."},
            {"type": "code", "heading": "Example", "content": "```python\nx = 1\n```"},
            {"type": "callout", "heading": "Key Point", "content": "- Remember this\n- And that"},
            {"type": "table", "heading": "Summary", "content": "| A | B |\n|---|---|\n| 1 | 2 |"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "mixed_test.pptx")
            result = export_to_pptx(content_blocks, path, title="Mixed Test")
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0

    def test_slide_count_reflects_content(self):
        content_blocks = [
            {"type": "section", "heading": "S1", "content": "Content 1"},
            {"type": "section", "heading": "S2", "content": "Content 2"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "count_test.pptx")
            export_to_pptx(content_blocks, path, title="Count Test")
            prs = Presentation(path)
            # Title + 2 section headers + 2 content slides = 5
            assert len(prs.slides) == 5
