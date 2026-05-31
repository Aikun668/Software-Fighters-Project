"""
题目 JSON 校验器 — 搬运自 DeepTutor pipeline.py 的 validate + normalize 流程。

搬法：搬代码（纯逻辑），适配我们 2 种题型（choice / short_answer）。
搬了什么：
  - _normalize_quiz_payload() 的规范化逻辑（字段 trim、options 过滤、correct_answer 对齐）
  - _collect_quiz_issues() 的问题检测（缺失字段、题型约束违规）
不搬什么：
  - _repair_quiz_payload() — LLM 修复循环，我们已有 _call_llm_json 重试
  - _parse_quiz_payload() — 已有 parse_llm_json
  - QuestionType StrEnum — 2 种题型用 frozenset 足够
"""

from typing import Any

_VALID_TYPES: frozenset[str] = frozenset({"choice", "short_answer"})
_CHOICE_KEYS: tuple[str, ...] = ("A", "B", "C", "D")


# ── public API ──────────────────────────────────────────────────


def validate_question(question: dict[str, Any]) -> tuple[dict, list[str]]:
    """
    规范化 + 检测 LLM 生成的题目问题。

    Returns:
        (normalized, issues): normalized 是修正后的题目 dict，
        issues 是检测到的问题列表（空列表 = 无问题）。
    """
    normalized = _normalize(question)
    issues = _collect_issues(normalized)
    return normalized, issues


# ── normalize ───────────────────────────────────────────────────


def _normalize(q: dict[str, Any]) -> dict[str, Any]:
    """规范化题目字段（搬自 DeepTutor _normalize_quiz_payload）"""
    out: dict[str, Any] = {}

    qtype = str(q.get("question_type", "")).strip().lower()
    if qtype not in _VALID_TYPES:
        qtype = "short_answer"
    out["question_type"] = qtype

    out["question"] = str(q.get("question", "") or "").strip()
    out["correct_answer"] = str(q.get("correct_answer", "") or "").strip()
    out["explanation"] = str(q.get("explanation", "") or "").strip()

    raw_opts = q.get("options")
    if qtype == "choice":
        out["options"] = _normalize_options(raw_opts)
        if out["options"] and out["correct_answer"]:
            out["correct_answer"] = _align_answer_key(out["options"], out["correct_answer"])
    else:
        out["options"] = None

    return out


def _normalize_options(raw: Any) -> dict[str, str] | None:
    """过滤 choice 选项：只保留 A/B/C/D 且值非空的条目"""
    if not isinstance(raw, dict):
        return None
    clean: dict[str, str] = {}
    for k, v in raw.items():
        key = str(k or "").strip().upper()[:1]
        val = str(v or "").strip()
        if key in _CHOICE_KEYS and val:
            clean[key] = val
    return clean if len(clean) == 4 else None


def _align_answer_key(options: dict[str, str], answer: str) -> str:
    """将 correct_answer 对齐到选项键 A/B/C/D"""
    upper = answer.upper().strip()
    if upper in options:
        return upper
    for key, text in options.items():
        if answer.lower() == str(text).lower():
            return key
    return answer


# ── collect issues ──────────────────────────────────────────────


def _collect_issues(q: dict[str, Any]) -> list[str]:
    """检测题目 schema 违规（搬自 DeepTutor _collect_quiz_issues）"""
    issues: list[str] = []

    question = str(q.get("question") or "").strip()
    correct = str(q.get("correct_answer") or "").strip()
    explanation = str(q.get("explanation") or "").strip()
    options = q.get("options")
    qtype = q.get("question_type", "")

    if not question:
        issues.append("missing_question")
    if not correct:
        issues.append("missing_correct_answer")
    if not explanation:
        issues.append("missing_explanation")

    if qtype == "choice":
        if not isinstance(options, dict) or set(options.keys()) != set(_CHOICE_KEYS):
            issues.append("choice_options_must_be_a_to_d")
        if correct.upper() not in _CHOICE_KEYS:
            issues.append("choice_correct_answer_must_be_option_key")
    else:
        if isinstance(options, dict) and options:
            issues.append("non_choice_must_not_have_options")
        if correct.upper() in _CHOICE_KEYS and len(correct) == 1:
            issues.append("non_choice_correct_answer_looks_like_option_key")

    return issues
