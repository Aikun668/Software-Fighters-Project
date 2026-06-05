import pytest

from app.services.analogy_library import (
    AnalogyEntry,
    AnalogyLibrary,
    BUILTIN_ANALOGIES,
    get_analogy_library,
)


# ═══════════════════════════════════════════════════════════════
# AnalogyLibrary.search
# ═══════════════════════════════════════════════════════════════

class TestAnalogyLibrarySearch:
    @pytest.fixture
    def lib(self):
        return AnalogyLibrary()

    def test_search_by_concept_name(self, lib):
        results = lib.search("神经网络")
        assert len(results) >= 1
        assert results[0].concept == "神经网络"

    def test_search_case_insensitive(self, lib):
        results = lib.search("神经网络")  # Chinese doesn't have case but tests concept
        assert len(results) >= 1

    def test_search_returns_max_3(self, lib):
        results = lib.search("学习")  # "学习" appears in many entries
        assert len(results) <= 3

    def test_search_no_match_returns_empty(self, lib):
        results = lib.search("不存在的概念xyz123")
        assert results == []

    def test_search_by_category_filter(self, lib):
        results = lib.search("决策树", category="ml")
        assert len(results) == 1
        assert results[0].concept == "决策树"

    def test_search_wrong_category_returns_empty(self, lib):
        results = lib.search("决策树", category="ai")
        assert results == []

    def test_search_matches_in_analogy_text(self, lib):
        results = lib.search("大脑")
        assert len(results) >= 1
        assert any("大脑" in r.analogy for r in results)


# ═══════════════════════════════════════════════════════════════
# AnalogyLibrary.get_for_concept
# ═══════════════════════════════════════════════════════════════

class TestAnalogyLibraryGetForConcept:
    @pytest.fixture
    def lib(self):
        return AnalogyLibrary()

    def test_returns_first_match(self, lib):
        entry = lib.get_for_concept("梯度下降")
        assert entry is not None
        assert entry.concept == "梯度下降"

    def test_returns_none_for_no_match(self, lib):
        entry = lib.get_for_concept("不存在")
        assert entry is None


# ═══════════════════════════════════════════════════════════════
# AnalogyLibrary.format_for_prompt
# ═══════════════════════════════════════════════════════════════

class TestAnalogyLibraryFormatForPrompt:
    @pytest.fixture
    def lib(self):
        return AnalogyLibrary()

    def test_formats_entry_with_label(self, lib):
        result = lib.format_for_prompt("过拟合")
        assert "【类比】" in result
        assert "过拟合" in result

    def test_empty_for_unknown_concept(self, lib):
        result = lib.format_for_prompt("不存在的概念")
        assert result == ""


# ═══════════════════════════════════════════════════════════════
# AnalogyLibrary.get_categories
# ═══════════════════════════════════════════════════════════════

class TestAnalogyLibraryGetCategories:
    def test_returns_all_builtin_categories(self):
        lib = AnalogyLibrary()
        cats = lib.get_categories()
        assert "ai" in cats
        assert "ml" in cats
        assert "dl" in cats
        assert len(cats) == len(BUILTIN_ANALOGIES)


# ═══════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════

class TestAnalogyLibrarySingleton:
    def test_returns_same_instance(self):
        a = get_analogy_library()
        b = get_analogy_library()
        assert a is b


# ═══════════════════════════════════════════════════════════════
# AnalogyEntry dataclass
# ═══════════════════════════════════════════════════════════════

class TestAnalogyEntry:
    def test_create_entry(self):
        entry = AnalogyEntry(
            concept="测试概念",
            analogy="测试类比",
            explanation="测试解释",
            category="测试分类",
        )
        assert entry.concept == "测试概念"
        assert entry.analogy == "测试类比"


# ═══════════════════════════════════════════════════════════════
# Builtin analogies integrity
# ═══════════════════════════════════════════════════════════════

class TestBuiltinAnalogies:
    def test_all_entries_have_non_empty_fields(self):
        for cat, entries in BUILTIN_ANALOGIES.items():
            for e in entries:
                assert e.concept, f"Empty concept in {cat}"
                assert e.analogy, f"Empty analogy in {cat}/{e.concept}"
                assert e.explanation, f"Empty explanation in {cat}/{e.concept}"
                assert e.category, f"Empty category in {cat}/{e.concept}"

    def test_no_duplicate_concepts(self):
        concepts = []
        for entries in BUILTIN_ANALOGIES.values():
            for e in entries:
                concepts.append(e.concept)
        assert len(concepts) == len(set(concepts)), f"Duplicate concepts: {[c for c in concepts if concepts.count(c) > 1]}"
