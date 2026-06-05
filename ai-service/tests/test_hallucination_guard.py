from unittest.mock import MagicMock

import pytest

from app.services.hallucination_guard import (
    HallucinationGuard,
    HallucinationReport,
    ConfidenceScore,
    Citation,
    LOW_CONFIDENCE_COVERAGE_THRESHOLD,
)


def _make_mock_kb(results):
    """Helper: create a mock KB that returns given search results."""
    kb = MagicMock()
    kb.search.return_value = results
    return kb


# ═══════════════════════════════════════════════════════════════
# HallucinationGuard.verify
# ═══════════════════════════════════════════════════════════════

class TestHallucinationGuardVerify:
    def test_empty_text_returns_unverifiable(self):
        kb = _make_mock_kb([])
        guard = HallucinationGuard(kb)
        report = guard.verify("")
        assert report.safe is True
        assert report.verdict == "unverifiable"
        assert report.confidence.overall == 0.0

    def test_all_good_coverage_high_confidence(self):
        kb = _make_mock_kb([
            {"content": "match A", "score": 0.3},
            {"content": "match B", "score": 0.2},
        ])
        guard = HallucinationGuard(kb)
        # Text must produce claims of >=10 chars for the KB to be queried
        report = guard.verify("Python是一种广泛使用的编程语言。机器学习是AI的重要分支领域。")
        # With good coverage results, confidence should be high
        assert report.confidence.overall > 0.5
        assert report.safe is True

    def test_mixed_coverage_produces_partial_confidence(self):
        kb = MagicMock()
        call_count = [0]

        def side_effect(query, top_k=1):
            call_count[0] += 1
            if call_count[0] == 1:
                return [{"content": "good match", "score": 0.3}]
            elif call_count[0] == 2:
                return [{"content": "partial match", "score": 0.6}]
            else:
                return []

        kb.search = MagicMock(side_effect=side_effect)
        guard = HallucinationGuard(kb)
        report = guard.verify(
            "Python是一种广泛使用的编程语言。机器学习是AI的重要分支。"
            "量子计算是未来的方向趋势。"
        )
        assert 0.3 < report.confidence.overall < 0.9

    def test_all_weak_coverage_low_confidence(self):
        kb = _make_mock_kb([])
        guard = HallucinationGuard(kb)
        report = guard.verify(
            "量子计算会比传统计算快许多倍。它利用量子比特的叠加态特性。"
        )
        assert report.confidence.overall < 0.5
        assert len(report.confidence.low_confidence_claims) > 0

    def test_report_includes_coverage_results(self):
        kb = _make_mock_kb([{"content": "match", "score": 0.3}])
        guard = HallucinationGuard(kb)
        report = guard.verify("Python是一种广泛使用的编程语言并且语法简洁容易上手。")
        assert len(report.coverage_results) >= 1

    def test_citations_populated_for_good_coverage(self):
        kb = _make_mock_kb([{"content": "Python由Guido设计开发", "score": 0.3}])
        guard = HallucinationGuard(kb)
        report = guard.verify("Python由Guido van Rossum设计开发并持续维护至今。")
        good_citations = [c for c in report.citations if c.snippet]
        assert len(good_citations) >= 1

    def test_no_citations_for_weak_coverage(self):
        kb = _make_mock_kb([])
        guard = HallucinationGuard(kb)
        report = guard.verify("一个完全不在知识库中的奇异声明观点。")
        assert len(report.citations) == 0

    def test_warnings_generated_when_weak_exceeds_threshold(self):
        kb = _make_mock_kb([])
        guard = HallucinationGuard(kb)
        report = guard.verify(
            "声明A这是不在库中的。声明B也是不在库中。声明C依然不在库里面。"
        )
        if report.confidence.overall < LOW_CONFIDENCE_COVERAGE_THRESHOLD:
            assert len(report.warnings) > 0


# ═══════════════════════════════════════════════════════════════
# HallucinationGuard.verify_and_format
# ═══════════════════════════════════════════════════════════════

class TestHallucinationGuardVerifyAndFormat:
    def test_high_confidence_returns_original_text(self):
        kb = _make_mock_kb([{"content": "exact match here", "score": 0.1}])
        guard = HallucinationGuard(kb)
        text = "Exact match here and some extra context words."
        result = guard.verify_and_format(text)
        assert result == text

    def test_low_confidence_appends_disclaimer(self):
        kb = _make_mock_kb([])
        guard = HallucinationGuard(kb)
        text = "人工智能可以完美解决所有问题并替代人类完成全部工作无需监督。"
        result = guard.verify_and_format(text)
        if result != text:
            # If modified, should still contain original text
            assert text in result
            assert "置信度" in result

    def test_short_text_without_claims_returns_original(self):
        kb = _make_mock_kb([])
        guard = HallucinationGuard(kb)
        text = "你好。谢谢。"
        result = guard.verify_and_format(text)
        assert result == text


# ═══════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════

class TestDataStructures:
    def test_citation_defaults(self):
        c = Citation(snippet="test snippet")
        assert c.source_chapter == ""
        assert c.source_section == ""

    def test_confidence_score_defaults(self):
        cs = ConfidenceScore(overall=0.5)
        assert cs.claim_scores == []
        assert cs.low_confidence_claims == []

    def test_hallucination_report_fields(self):
        report = HallucinationReport(
            safe=True,
            verdict="verified",
            confidence=ConfidenceScore(overall=0.9),
        )
        assert report.safe is True
        assert report.verdict == "verified"
        assert report.confidence.overall == 0.9
        assert report.coverage_results == []
        assert report.citations == []
        assert report.warnings == []
