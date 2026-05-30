import json
import pytest
from app.utils.json_parser import parse_llm_json


class TestParseLlmJson:
    def test_normal_json(self):
        result = parse_llm_json('{"key": "value", "num": 42}')
        assert result == {"key": "value", "num": 42}

    def test_markdown_code_block(self):
        text = "```json\n{\"key\": \"value\"}\n```"
        result = parse_llm_json(text)
        assert result == {"key": "value"}

    def test_markdown_without_json_label(self):
        text = "```\n{\"key\": \"value\"}\n```"
        result = parse_llm_json(text)
        assert result == {"key": "value"}

    def test_nested_markdown(self):
        text = "Some text\n```json\n{\"updates\": {\"knowledge_base\": 30}}\n```\nMore text"
        result = parse_llm_json(text)
        assert result == {"updates": {"knowledge_base": 30}}

    def test_empty_string(self):
        result = parse_llm_json("")
        assert result == {}

    def test_whitespace_only(self):
        result = parse_llm_json("   \n\t  ")
        assert result == {}

    def test_non_json_text(self):
        result = parse_llm_json("This is not JSON at all")
        assert result == {}

    def test_custom_fallback(self):
        result = parse_llm_json("invalid", fallback={"default": True})
        assert result == {"default": True}

    def test_expected_key_present(self):
        result = parse_llm_json('{"templates": [{"id": 1}]}', expected_key="templates")
        assert result == {"templates": [{"id": 1}]}

    def test_expected_key_missing(self):
        result = parse_llm_json('{"other": "value"}', expected_key="templates", fallback={"templates": []})
        assert result == {"templates": []}

    def test_broken_json_with_repair(self):
        text = '{"key": "value"'
        result = parse_llm_json(text)
        assert result == {"key": "value"}

    def test_unicode_content(self):
        text = '{"content": "你好世界"}'
        result = parse_llm_json(text)
        assert result["content"] == "你好世界"

    def test_list_response(self):
        result = parse_llm_json('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_scalar_fallback(self):
        result = parse_llm_json("invalid", fallback=None)
        assert result is None
