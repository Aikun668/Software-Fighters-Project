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
    """Detects unsafe patterns in LLM-generated content."""

    CODE_INJECTION = re.compile(
        r'```(python|bash|sql|javascript)\s+'
        r'(?![\s\S]*?(?:#|//|/\*)[\s\S]*?(?:避免|不要|禁止|错误|BAD|WRONG|Anti?-?pattern))'
        r'[\s\S]*?\b(?:exec\s*\(|eval\s*\(|os\.system\s*\(|subprocess\.call|rm\s+-rf\s+/)',
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

        if cls.CODE_INJECTION.search(text):
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
                docs = kb.search(claim, top_k=1)
                if docs:
                    score = cls._normalize_score(docs[0].get("score", 1.0))
                else:
                    score = 1.0
                if score < GOOD_COVERAGE_THRESHOLD:
                    results.append(CoverageResult(
                        claim=claim,
                        coverage="GOOD",
                        evidence=docs[0]["content"][:200],
                    ))
                elif score < PARTIAL_COVERAGE_THRESHOLD:
                    results.append(CoverageResult(
                        claim=claim,
                        coverage="PARTIAL",
                        evidence=docs[0]["content"][:200],
                    ))
                else:
                    results.append(CoverageResult(
                        claim=claim,
                        coverage="WEAK",
                        evidence="",
                    ))
            except Exception:
                logger.warning(f"KB coverage check failed for claim: {claim[:80]}", exc_info=True)
                results.append(CoverageResult(claim=claim, coverage="WEAK", evidence=""))

        return results
