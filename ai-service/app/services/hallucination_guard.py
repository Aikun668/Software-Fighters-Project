import logging
from dataclasses import dataclass, field
from typing import Optional

from app.utils.content_guard import KBCoverageChecker, CoverageResult, SearchableKB

logger = logging.getLogger(__name__)

LOW_CONFIDENCE_COVERAGE_THRESHOLD = 0.5
HIGH_CONFIDENCE_COVERAGE_THRESHOLD = 0.85

GOOD_CLAIM_SCORE = 0.9
PARTIAL_CLAIM_SCORE = 0.6
WEAK_CLAIM_SCORE = 0.2


@dataclass
class Citation:
    source_chapter: str = ""
    source_section: str = ""
    snippet: str = ""


@dataclass
class ConfidenceScore:
    overall: float
    claim_scores: list[float] = field(default_factory=list)
    low_confidence_claims: list[str] = field(default_factory=list)


@dataclass
class HallucinationReport:
    safe: bool
    verdict: str  # "verified" | "unverifiable" | "mixed" — 区分"验证通过"和"无法验证"
    confidence: ConfidenceScore
    coverage_results: list[CoverageResult] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class HallucinationGuard:
    def __init__(self, kb: SearchableKB):
        self.kb = kb

    def verify(self, text: str) -> HallucinationReport:
        coverage_results = KBCoverageChecker.check_coverage(text, self.kb)
        if not coverage_results:
            # 文本中无可提取的事实声明（如纯闲聊/问候），无法进行 KB 覆盖率验证
            # 这不等同于"验证通过"——设为 unverifiable，由调用方决定如何处理
            return HallucinationReport(
                safe=True,
                verdict="unverifiable",
                confidence=ConfidenceScore(overall=0.0),
            )

        total = len(coverage_results)
        weak_count = sum(1 for r in coverage_results if r.coverage == "WEAK")

        claim_scores = []
        for r in coverage_results:
            if r.coverage == "GOOD":
                claim_scores.append(GOOD_CLAIM_SCORE)
            elif r.coverage == "PARTIAL":
                claim_scores.append(PARTIAL_CLAIM_SCORE)
            else:
                claim_scores.append(WEAK_CLAIM_SCORE)

        overall = sum(claim_scores) / len(claim_scores) if claim_scores else 0.5

        low_confidence_claims = [
            r.claim for r in coverage_results
            if r.coverage == "WEAK"
        ]

        warnings = []
        if weak_count / total > LOW_CONFIDENCE_COVERAGE_THRESHOLD:
            warnings.append(f"超过{int(LOW_CONFIDENCE_COVERAGE_THRESHOLD*100)}%的内容在知识库中无法验证，可能存在幻觉")
        if low_confidence_claims:
            warnings.append(f"{len(low_confidence_claims)}条声明置信度较低，建议核实")

        citations = []
        for r in coverage_results:
            if r.evidence and r.coverage in ("GOOD", "PARTIAL"):
                # 尝试从 KB 检索结果中提取章节信息（若 KB 条目包含元数据）
                evidence_dict = r.evidence if isinstance(r.evidence, dict) else {}
                citations.append(Citation(
                    source_chapter=evidence_dict.get("chapter", "") if isinstance(r.evidence, dict) else "",
                    source_section=evidence_dict.get("section", "") if isinstance(r.evidence, dict) else "",
                    snippet=r.evidence[:200] if isinstance(r.evidence, str) else str(r.evidence)[:200],
                ))

        safe = overall >= 0.5

        if overall >= HIGH_CONFIDENCE_COVERAGE_THRESHOLD:
            verdict = "verified"
        elif overall >= LOW_CONFIDENCE_COVERAGE_THRESHOLD:
            verdict = "mixed"
        else:
            verdict = "unverifiable"

        return HallucinationReport(
            safe=safe,
            verdict=verdict,
            confidence=ConfidenceScore(
                overall=round(overall, 2),
                claim_scores=[round(s, 2) for s in claim_scores],
                low_confidence_claims=low_confidence_claims[:10],
            ),
            coverage_results=coverage_results,
            citations=citations,
            warnings=warnings,
        )

    def verify_and_format(self, text: str) -> str:
        report = self.verify(text)

        # 无法验证（无可提取事实声明）— 不附加警告，避免误报
        if report.verdict == "unverifiable" and not report.coverage_results:
            return text

        if report.confidence.overall >= LOW_CONFIDENCE_COVERAGE_THRESHOLD:
            if report.warnings:
                logger.info("Hallucination guard — report (verdict=%s, confidence=%.2f): %s",
                             report.verdict, report.confidence.overall, report.warnings)
            return text

        # Only add disclaimers when confidence is critically low
        logger.warning("Hallucination guard — LOW confidence (verdict=%s, %.2f): %s",
                       report.verdict, report.confidence.overall, report.warnings)

        parts = [text]

        if report.warnings:
            parts.append("\n---")
            parts.append("**内容核查提示：**")
            for w in report.warnings:
                parts.append(f"- {w}")

        if report.confidence.low_confidence_claims:
            parts.append("\n**以下内容置信度较低，仅供参考：**")
            for claim in report.confidence.low_confidence_claims[:3]:
                parts.append(f"- {claim[:100]}")

        return "\n".join(parts)