"""
Content safety filter and knowledge-base coverage checker for LLM outputs.
KBCoverageChecker checks whether claims find supporting text in the KB,
NOT whether the claims are factually true.
Vector similarity != fact verification.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)

# KBCoverage thresholds (cosine distance: 0=identical, 2=opposite)
GOOD_COVERAGE_THRESHOLD = 0.5
PARTIAL_COVERAGE_THRESHOLD = 0.8
MIN_CLAIM_LENGTH = 10
MAX_QUERY_LENGTH = 500

GREETING_KEYWORDS = ['你好', '欢迎', '请问', '谢谢']


class SearchableKB(Protocol):
    def search(self, query: str, top_k: int = 1) -> list[dict]: ...


@dataclass
class SafetyResult:
    safe: bool
    violations: list[str] = field(default_factory=list)


@dataclass
class CoverageResult:
    claim: str
    coverage: str  # GOOD / PARTIAL / WEAK
    evidence: str = ""


class ContentSafetyFilter:
    """Detects unsafe patterns in LLM-generated content.

    Separates dangerous-pattern detection from educational-context detection,
    rather than using a single fragile negative-lookahead regex that can be
    bypassed with encoding tricks or unusual formatting.
    """

    DANGEROUS_CODE = re.compile(
        r'```(?:python|bash|sql|javascript|sh)\s*[\s\S]*?\b(?:exec\s*\(|eval\s*\(|os\.system\s*\(|subprocess\.call|rm\s+-rf\s+/)',
        re.IGNORECASE,
    )
    EDUCATIONAL_CONTEXT = re.compile(
        r'(?:避免|不要|禁止|错误示例|反面|BAD|WRONG|Anti-?pattern|'
        r'不要这样做|切勿|严禁|危险|教学用|示例|example\s+of\s+what\s+not)',
        re.IGNORECASE,
    )
    JAILBREAK = re.compile(
        r'(ignore|forget|disregard)\s+(all\s+)?(previous|above|your)\s+(instructions|rules|prompt)',
        re.IGNORECASE,
    )
    LINK_OBFUSCATION = re.compile(r'\[.*?\]\(javascript:', re.IGNORECASE)
    SENSITIVE_KEYWORDS = re.compile(
        r'(hack|exploit|bypass\s+security|steal\s+password)', re.IGNORECASE
    )

    @classmethod
    def check(cls, text: str) -> SafetyResult:
        violations = []

        if cls.DANGEROUS_CODE.search(text) and not cls.EDUCATIONAL_CONTEXT.search(text):
            violations.append("code_injection")
        if cls.JAILBREAK.search(text):
            violations.append("jailbreak_attempt")
        if cls.LINK_OBFUSCATION.search(text):
            violations.append("link_obfuscation")
        if cls.SENSITIVE_KEYWORDS.search(text):
            violations.append("sensitive_keywords")

        return SafetyResult(safe=len(violations) == 0, violations=violations)


class KBCoverageChecker:
    """Checks whether claims can find supporting text in the knowledge base.

    This is a KB coverage check, NOT fact verification.
    GOOD coverage = similar text exists in KB. It does NOT mean the claim is true.
    The final judgment belongs to the student or teacher, not this checker.
    """

    CLAIM_SEPARATORS = re.compile(r'[。！；\n.!?]')

    @staticmethod
    def _sanitize_query(text: str) -> str:
        """Truncate and strip control characters from KB search queries."""
        cleaned = text.translate(dict.fromkeys(range(32)))
        return cleaned[:MAX_QUERY_LENGTH].strip()

    @staticmethod
    def _normalize_score(score: float) -> float:
        """Normalize KB search score to cosine-distance scale [0, 2].
        ChromaDB cosine: 0=identical, 2=opposite.
        Keyword fallback: integer count, higher = more overlap.
        Returns values > 2.0 (non-cosine counts) remapped to 0-2 range."""
        if isinstance(score, (int, float)) and score > 2.0:
            if score >= 10:
                return 0.2
            elif score >= 5:
                return 0.5
            else:
                return 0.75
        return float(score)

    @classmethod
    def extract_claims(cls, text: str) -> list[str]:
        """Split text into individual factual claims, skipping questions and short fragments."""
        parts = cls.CLAIM_SEPARATORS.split(text)
        claims = []
        for part in parts:
            part = part.strip()
            if len(part) < MIN_CLAIM_LENGTH:
                continue
            if part.endswith(('?', '？')):
                continue
            if any(kw in part for kw in GREETING_KEYWORDS):
                continue
            claims.append(part)
        return claims

    @classmethod
    def check_coverage(cls, text: str, kb: SearchableKB) -> list[CoverageResult]:
        """Extract claims and check KB coverage for each. Returns coverage level per claim."""
        claims = cls.extract_claims(text)
        if not claims:
            return []

        results = []
        for claim in claims:
            try:
                query = cls._sanitize_query(claim)
                if not query:
                    results.append(CoverageResult(claim=claim, coverage="WEAK", evidence=""))
                    continue
                docs = kb.search(query, top_k=1)
                if docs:
                    score = cls._normalize_score(docs[0].get("score", 1.0))
                    evidence = str(docs[0].get("content", ""))[:200] if isinstance(docs[0], dict) else ""
                else:
                    score = 1.0
                    evidence = ""
                if score < GOOD_COVERAGE_THRESHOLD:
                    results.append(CoverageResult(
                        claim=claim, coverage="GOOD", evidence=evidence,
                    ))
                elif score < PARTIAL_COVERAGE_THRESHOLD:
                    results.append(CoverageResult(
                        claim=claim, coverage="PARTIAL", evidence=evidence,
                    ))
                else:
                    results.append(CoverageResult(
                        claim=claim, coverage="WEAK", evidence="",
                    ))
            except Exception:
                logger.warning(f"KB coverage check failed for claim: {claim[:80]}", exc_info=True)
                results.append(CoverageResult(claim=claim, coverage="WEAK", evidence=""))

        return results


class SafetyPipeline:

    # 检测个人敏感信息：身份证/银行卡关键词
    # 已移除 1[3-9]\d{9} 裸数字模式 — AI 教学回答中经常出现 11 位数字串
    # （参数值、计算步骤、统计数字等），与手机号格式无法区分，误报率过高。
    # 手机号检测改为仅匹配带分隔符的格式（138-0000-0000 / 138 0000 0000），
    # 这种格式在文本中出现时几乎一定是刻意写的手机号，不会是教学数字。
    PERSONAL_INFO_KEYWORDS = re.compile(
        r'(身份证|身份证号|银行卡|手机号)',
    )
    PHONE_FORMATTED = re.compile(
        r'1[3-9]\d[-\s]\d{4}[-\s]\d{4}',
    )
    VIOLENCE = re.compile(
        r'(杀人|枪支|爆炸|自杀|自残|投毒)',
    )
    # AI/ML 教学场景中的技术术语包含"爆炸"，不应视为暴力内容
    TECHNICAL_EXPLOSION = re.compile(
        r'(梯度爆炸|参数爆炸|维度爆炸|组合爆炸|信息爆炸|数据爆炸|指数爆炸)',
    )
    HATE_SPEECH = re.compile(
        r'(种族歧视|性别歧视|地域歧视|宗教歧视|政治敏感)',
    )
    PORNOGRAPHY = re.compile(
        r'(色情|淫秽|裸体|性暗示)',
    )
    # 过度自信标记 — 匹配"绝对能/一定能/100%会"等绝对化表述
    # 注意：教育场景中"你绝对能做到"是鼓励语，非虚假信息
    # 通过 EDUCATIONAL_ENCOURAGEMENT 排除此类误报
    MISINFO_MARKERS = re.compile(
        r'(绝对|肯定|一定|100%|毫无疑问)\s*(能|可以|会|是)',
    )
    # 教育鼓励语境——匹配"你/我们 + 绝对/一定 + 能/会"等表述，这些是正向激励非 misinformation
    EDUCATIONAL_ENCOURAGEMENT = re.compile(
        r'(你|我们|大家)\S{0,5}(绝对|肯定|一定|毫无疑问)\S{0,5}(能|可以|会)',
    )

    @classmethod
    def check(cls, text: str) -> SafetyResult:
        base = ContentSafetyFilter.check(text)
        violations = list(base.violations)  # defensive copy — don't mutate

        if cls.PERSONAL_INFO_KEYWORDS.search(text):
            violations.append("personal_info")
        if cls.PHONE_FORMATTED.search(text) and "personal_info" not in violations:
            violations.append("personal_info")
        cleaned = cls.TECHNICAL_EXPLOSION.sub('', text)
        if cls.VIOLENCE.search(cleaned):
            violations.append("violence")
        if cls.HATE_SPEECH.search(text):
            violations.append("hate_speech")
        if cls.PORNOGRAPHY.search(text):
            violations.append("pornography")
        # RL/AI 术语上下文豁免：PPO/Agent/Policy 等技术讨论中的"肯定能"不构成过度自信
        rl_context = bool(re.search(
            r'(?:PPO|RL|Policy\s*Gradient|Reward\s*Model|Critic|Actor|'
            r'微调|fine.?tune|算法|模型|训练|梯度|参数|优化|推理|架构)',
            text, re.IGNORECASE,
        ))
        if (cls.MISINFO_MARKERS.search(text)
            and not cls.EDUCATIONAL_ENCOURAGEMENT.search(text)
            and not rl_context):
            violations.append("overconfident_language")

        return SafetyResult(safe=len(violations) == 0, violations=violations)

    @classmethod
    def check_with_kb(
        cls, text: str, kb: SearchableKB
    ) -> tuple[SafetyResult, list[CoverageResult]]:
        safety_result = cls.check(text)
        coverage_results = KBCoverageChecker.check_coverage(text, kb)
        return safety_result, coverage_results


@dataclass
class ConfidenceResult:
    score: float
    label: str
    markup: str


def compute_confidence(coverage_results: list[CoverageResult]) -> ConfidenceResult:
    if not coverage_results:
        return ConfidenceResult(score=0.5, label="未知", markup="")

    good = sum(1 for r in coverage_results if r.coverage == "GOOD")
    partial = sum(1 for r in coverage_results if r.coverage == "PARTIAL")
    total = len(coverage_results)
    score = (good * 1.0 + partial * 0.5) / total if total > 0 else 0.5

    if score >= 0.8:
        label = "高置信度"
        markup = ""
    elif score >= 0.5:
        label = "中等置信度"
        markup = "部分内容需核实"
    else:
        label = "低置信度"
        markup = "以下内容仅供参考，可能存在不准确之处"

    return ConfidenceResult(score=round(score, 2), label=label, markup=markup)
