import logging
from dataclasses import dataclass, field
from functools import wraps
from typing import Optional

from app.utils.content_guard import KBCoverageChecker, CoverageResult, SearchableKB
from app.utils.security_logger import SecurityLogger

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
            warnings.append(f"超过{int(LOW_CONFIDENCE_COVERAGE_THRESHOLD*100)}%的内容未在教材中找到对应验证，建议结合教材核实")
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
        """校验文本并记录低置信警告，正文原样返回。

        P4 评审 af-01：旧实现曾把"内容核查提示：…以下内容置信度较低，仅供参考：…"
        等 QA 管线内部文本追加进回答正文（60 条真实回答中 15 条命中），且追加发生在
        sanity 检查之后、无法被拦截。现在核查详情只进日志；用户侧免责声明由
        kb_verify 的 DISCLAIMER_TEXT 统一承担；结构化报告仍可经 verify() 获取，
        供将来做成前端独立 UI 元素。
        """
        report = self.verify(text)

        # 无法验证（无可提取事实声明）— 无需警告
        if report.verdict == "unverifiable" and not report.coverage_results:
            return text

        if report.confidence.overall >= LOW_CONFIDENCE_COVERAGE_THRESHOLD:
            if report.warnings:
                logger.info("Hallucination guard — report (verdict=%s, confidence=%.2f): %s",
                             report.verdict, report.confidence.overall, report.warnings)
            return text

        logger.warning("Hallucination guard — LOW confidence (verdict=%s, %.2f): %s",
                       report.verdict, report.confidence.overall, report.warnings)
        return text


DISCLAIMER_TEXT = "\n\n> 以上部分内容未在教材中找到对应验证，建议结合教材核实。"


def kb_verify(fields: list[str]):
    """类装饰器：在 Agent.run() 返回前对指定字段做 KB 覆盖验证。

    用法：
        @kb_verify(fields=["response"])
        class TutorAgent(BaseAgent):
            ...

        @kb_verify(fields=["questions[*].question", "questions[*].answer"])
        class ExerciseAgent(BaseAgent):
            ...

    - ``fields`` 中的路径支持 ``key[*].subkey`` 语法，表示遍历列表中每个元素的 subkey。
    - 验证失败时不阻断返回，仅在低置信度文本后附加 DISCLAIMER_TEXT。
    - KB 不可用时静默降级，不抛异常。
    """
    def decorator(cls):
        original_run = cls.run

        @wraps(original_run)
        async def safe_run(self, input_state: dict) -> dict:
            output = await original_run(self, input_state)
            try:
                from app.services.knowledge_base import get_kb
                kb = get_kb()
                guard = HallucinationGuard(kb)

                for field_path in fields:
                    _verify_field(output, field_path, guard, input_state.get("user_id"), cls.__name__)
            except Exception:
                logger.warning("kb_verify failed for agent=%s, returning raw output", cls.__name__, exc_info=True)
                SecurityLogger.log_event(
                    "pipeline_error",
                    {"agent": cls.__name__, "user_id": input_state.get("user_id"), "content": ""},
                    severity="low",
                )
            return output

        cls.run = safe_run
        return cls

    return decorator


def _verify_field(
    obj: dict,
    field_path: str,
    guard: HallucinationGuard,
    user_id,
    agent_name: str,
) -> None:
    parts = field_path.split(".")
    _descend(obj, parts, guard, user_id, agent_name)


def _descend(
    obj,
    parts: list[str],
    guard: HallucinationGuard,
    user_id,
    agent_name: str,
) -> None:
    if not parts:
        return

    head, *tail = parts

    # list traversal: key[*] → iterate list items
    if head.endswith("[*]"):
        list_key = head[:-3]
        items = obj.get(list_key)
        if not isinstance(items, list):
            return
        for item in items:
            if isinstance(item, dict):
                _descend(item, tail, guard, user_id, agent_name)
    else:
        val = obj.get(head)
        if isinstance(val, str) and not tail:
            # leaf: verify this text field
            if len(val) >= 20:  # skip very short strings
                report = guard.verify(val)
                # 没有任何 GOOD/PARTIAL 声明 → 文本无可验证内容（系统报错/兜底文案），跳过
                has_any_support = any(
                    r.coverage in ("GOOD", "PARTIAL") for r in report.coverage_results
                )
                if not has_any_support:
                    return
                if report.confidence.overall < LOW_CONFIDENCE_COVERAGE_THRESHOLD:
                    obj[head] = val + DISCLAIMER_TEXT
                    SecurityLogger.log_event(
                        "hallucination_warning",
                        {
                            "agent": agent_name,
                            "user_id": user_id,
                            "content": val,
                            "extra": {
                                "field": head,
                                "confidence": report.confidence.overall,
                                "verdict": report.verdict,
                            },
                        },
                        severity="low",
                    )
        elif isinstance(val, dict) and tail:
            _descend(val, tail, guard, user_id, agent_name)
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    _descend(item, tail, guard, user_id, agent_name)