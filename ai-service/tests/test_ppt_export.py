import os
import tempfile

import pytest

from app.utils.ppt_exporter import export_to_pptx


class TestExportToPptx:
    def test_export_to_pptx_creates_file(self):
        content_blocks = [
            {"type": "section", "heading": "Intro", "content": "Welcome to AI"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_output.pptx")
            result = export_to_pptx(content_blocks, output_path, title="Test")
            assert result == output_path
            assert os.path.exists(output_path)
            assert os.path.getsize(output_path) > 0

    def test_export_to_pptx_section_block(self):
        content_blocks = [
            {"type": "section", "heading":"Chapter 1", "content": "This is a section"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "section_test.pptx")
            result = export_to_pptx(content_blocks, output_path, title="Test")
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0

    def test_export_to_pptx_code_block(self):
        content_blocks = [
            {"type": "code", "heading":"Hello World", "content": "print('hello')"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "code_test.pptx")
            result = export_to_pptx(content_blocks, output_path, title="Test")
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0

    def test_export_to_pptx_callout_block(self):
        content_blocks = [
            {"type": "callout", "heading":"Important", "content": "Pay attention!"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "callout_test.pptx")
            result = export_to_pptx(content_blocks, output_path, title="Test")
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0

    def test_export_to_pptx_empty_blocks(self):
        content_blocks = []
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "empty_test.pptx")
            result = export_to_pptx(content_blocks, output_path, title="Test")
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0

    def test_export_to_pptx_text_block(self):
        content_blocks = [
            {"type": "text", "heading":"Note", "content": "Some text here"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "text_test.pptx")
            result = export_to_pptx(content_blocks, output_path, title="Test")
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0

    def test_export_to_pptx_mindmap_block(self):
        content_blocks = [
            {"type": "mindmap", "heading":"Mindmap", "content": "mindmap content"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "mindmap_test.pptx")
            result = export_to_pptx(content_blocks, output_path, title="Test")
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0

    def test_export_to_pptx_creates_parent_dirs(self):
        content_blocks = [
            {"type": "text", "heading":"T", "content": "C"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_path = os.path.join(tmpdir, "sub", "nested", "output.pptx")
            result = export_to_pptx(content_blocks, nested_path, title="Test")
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0
