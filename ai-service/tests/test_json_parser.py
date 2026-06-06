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


# ═══════════════════════════════════════════════════════════════
# Bracket-balanced extraction tests (Phase 4.1)
# ═══════════════════════════════════════════════════════════════


class TestBracketExtraction:
    def test_simple_object_in_prose(self):
        from app.utils.json_parser import _extract_bracket_balanced

        text = 'Some prefix text {"key": "val"} and suffix'
        extracted = _extract_bracket_balanced(text)
        assert extracted == '{"key": "val"}'

    def test_array_in_prose(self):
        from app.utils.json_parser import _extract_bracket_balanced

        text = "before [1, 2, 3] after"
        extracted = _extract_bracket_balanced(text)
        assert extracted == "[1, 2, 3]"

    def test_nested_braces(self):
        from app.utils.json_parser import _extract_bracket_balanced

        text = '{"outer": {"inner": "val"}} tail'
        extracted = _extract_bracket_balanced(text)
        assert extracted == '{"outer": {"inner": "val"}}'

    def test_no_bracket_returns_none(self):
        from app.utils.json_parser import _extract_bracket_balanced

        assert _extract_bracket_balanced("no brackets here") is None

    def test_unclosed_bracket_returns_none(self):
        from app.utils.json_parser import _extract_bracket_balanced

        assert _extract_bracket_balanced('{"key": "val"') is None

    def test_bracket_in_string_ignored(self):
        from app.utils.json_parser import _extract_bracket_balanced

        text = '{"key": "hello { world }"} end'
        extracted = _extract_bracket_balanced(text)
        assert extracted == '{"key": "hello { world }"}'

    def test_escaped_quote_in_string(self):
        from app.utils.json_parser import _extract_bracket_balanced

        text = '{"key": "val\\"ue"} after'
        extracted = _extract_bracket_balanced(text)
        assert extracted == '{"key": "val\\"ue"}'


class TestCommonJsonFix:
    def test_unquoted_property_names(self):
        from app.utils.json_parser import _fix_common_json_issues
        import json as _json

        fixed = _fix_common_json_issues('{key: "val", num: 42}')
        parsed = _json.loads(fixed)
        assert parsed == {"key": "val", "num": 42}

    def test_trailing_comma_in_object(self):
        from app.utils.json_parser import _fix_common_json_issues
        import json as _json

        fixed = _fix_common_json_issues('{"a": 1,}')
        parsed = _json.loads(fixed)
        assert parsed == {"a": 1}

    def test_trailing_comma_in_array(self):
        from app.utils.json_parser import _fix_common_json_issues
        import json as _json

        fixed = _fix_common_json_issues("[1, 2,]")
        parsed = _json.loads(fixed)
        assert parsed == [1, 2]

    def test_double_escaped_backslash(self):
        from app.utils.json_parser import _fix_common_json_issues

        fixed = _fix_common_json_issues('{"text": "line\\\\n"}')
        assert "\\\\n" not in fixed


class TestTryParseJson:
    def test_direct_parse_succeeds(self):
        from app.utils.json_parser import _try_parse_json

        result = _try_parse_json('{"a": 1}')
        assert result == {"a": 1}

    def test_common_fix_rescues(self):
        from app.utils.json_parser import _try_parse_json

        result = _try_parse_json('{key: "hello", num: 42,}')
        assert result == {"key": "hello", "num": 42}

    def test_all_strategies_fail_raises(self):
        from app.utils.json_parser import _try_parse_json
        import pytest

        with pytest.raises(ValueError, match="All parse strategies failed"):
            _try_parse_json("absolutely not JSON in any recoverable way")


class TestParseLlmJsonEnhanced:
    """Phase 4.1: 3 种提取 × 4 种修复的组合测试"""

    def test_json_embedded_in_prose_without_code_fence(self):
        text = '以下是生成的学习计划：\n{"topic": "Python", "steps": 5}\n请确认。'
        result = parse_llm_json(text)
        assert result == {"topic": "Python", "steps": 5}

    def test_bracket_match_with_repair(self):
        text = '输出: {key: "value", count: 3,} 完成'
        result = parse_llm_json(text)
        assert result == {"key": "value", "count": 3}

    def test_code_block_takes_priority(self):
        text = 'before {wrong: 1}\n```json\n{"correct": 2}\n```\nafter {also: wrong}'
        result = parse_llm_json(text)
        assert result == {"correct": 2}
