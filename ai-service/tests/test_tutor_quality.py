"""Tests for AnalogyLibrary — 内置类比库搜索和格式化"""
import pytest

from app.services.analogy_library import AnalogyLibrary, AnalogyEntry, get_analogy_library


class TestAnalogyLibrary:
    def test_search_by_concept(self):
        lib = AnalogyLibrary()
        results = lib.search("神经网络")
        assert len(results) > 0
        assert results[0].concept == "神经网络"

    def test_search_by_keyword(self):
        lib = AnalogyLibrary()
        results = lib.search("梯度")
        assert len(results) > 0
        assert any("梯度" in r.concept for r in results)

    def test_search_no_match(self):
        lib = AnalogyLibrary()
        results = lib.search("不存在的概念xyz")
        assert len(results) == 0

    def test_get_for_concept(self):
        lib = AnalogyLibrary()
        entry = lib.get_for_concept("过拟合")
        assert entry is not None
        assert "过拟合" in entry.concept

    def test_get_for_concept_not_found(self):
        lib = AnalogyLibrary()
        entry = lib.get_for_concept("不存在")
        assert entry is None

    def test_format_for_prompt(self):
        lib = AnalogyLibrary()
        result = lib.format_for_prompt("注意力机制")
        assert "类比" in result
        assert "注意力" in result

    def test_format_for_prompt_not_found(self):
        lib = AnalogyLibrary()
        result = lib.format_for_prompt("不存在")
        assert result == ""

    def test_get_categories(self):
        lib = AnalogyLibrary()
        cats = lib.get_categories()
        assert "ai" in cats
        assert "ml" in cats
        assert "dl" in cats

    def test_search_by_category(self):
        lib = AnalogyLibrary()
        results = lib.search("决策树", category="ml")
        assert len(results) > 0

    def test_singleton(self):
        lib1 = get_analogy_library()
        lib2 = get_analogy_library()
        assert lib1 is lib2


class TestAnalogyEntry:
    def test_entry_creation(self):
        entry = AnalogyEntry(
            concept="测试",
            analogy="测试类比",
            explanation="测试解释",
            category="测试类",
        )
        assert entry.concept == "测试"
        assert entry.analogy == "测试类比"
        assert entry.explanation == "测试解释"
        assert entry.category == "测试类"
