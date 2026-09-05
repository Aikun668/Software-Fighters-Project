"""ResponseSanityCheck — 输出健全性检查与一次重试（对话底座救援 · Task 8）。

设计约束（设计文档 · ResponseSanityCheck）：
- 第一轮只检查高置信异常：空回答、过度重复、明显截断、内部提示词/JSON 泄露、
  请求语言明显不一致。不做"事实是否正确"的判定。
- 最多以相同 BuiltContext 重试一次；再次失败返回可恢复错误与脱敏 error_code。
- 检查器不得改写正常回答（ACCEPT 时原文返回）。

截断判定刻意保守（避免误伤列表/代码/无句号结尾的正常回答）：
只认未闭合代码围栏、悬空连接标点（，、：；等）与未闭合括号三类强信号。
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum

# 高置信内部提示字段：整条回答被解析为 JSON 且含这些键时判定泄露。
# 刻意不用 system/context/profile 等教学示例常见键，避免误伤讲解 JSON 的回答。
_INTERNAL_JSON_KEYS = frozenset({
    "system_prompt", "built_context", "student_profile", "prompt_template",
    "messages_history", "internal_instructions", "few_shot", "kb_evidence",
})

# 未闭合代码围栏：``` 出现奇数次
_FENCE_RE = re.compile(r"```")

# 悬空连接标点：句子明显没说完
_DANGLING_END_RE = re.compile(r"[，、：；,;\-（【\[\{]$")

# 终端标点（用于切分重复片段）
_FRAGMENT_SPLIT_RE = re.compile(r"[。！？!?\n；;，,]+")

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


class SanityVerdict(str, Enum):
    ACCEPT = "ACCEPT"
    RETRY_ONCE = "RETRY_ONCE"
    USER_SAFE_ERROR = "USER_SAFE_ERROR"


ERROR_CODES: dict[str, str] = {
    "empty": "EMPTY_RESPONSE",
    "heavy_repetition": "HEAVY_REPETITION",
    "truncated": "TRUNCATED_RESPONSE",
    "prompt_leak": "PROMPT_LEAK",
    "language_mismatch": "LANGUAGE_MISMATCH",
}


@dataclass
class SanityResult:
    """单次检查结果。text 仅在 ACCEPT 时为原文（绝不改写）。"""
    verdict: SanityVerdict
    reason: str
    error_code: str | None = None
    text: str | None = None
    detail: str = ""  # 人工可读说明，脱敏：不携带回答原文片段


@dataclass
class SanityOutcome:
    """重试编排结果。text 为 None 表示调用方必须转成安全错误（不伪造 content）。"""
    text: str | None
    verdict: SanityVerdict
    error_code: str | None
    attempts: int
    failure_reasons: list[str] = field(default_factory=list)


def _is_empty(text: str | None) -> bool:
    return not text or not text.strip()


def _has_prompt_leak(text: str) -> bool:
    stripped = text.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return False
    try:
        data = json.loads(stripped)
    except (ValueError, TypeError):
        return False
    if not isinstance(data, dict):
        return False
    return bool(set(data.keys()) & _INTERNAL_JSON_KEYS)


def _has_heavy_repetition(text: str) -> bool:
    # 退化情形：长文本但字符种类极少（如 "哈"×200）
    compact = "".join(text.split())
    if len(compact) >= 60 and len(set(compact)) <= 4:
        return True
    # 片段重复：同一片段出现 ≥5 次且覆盖 ≥30% 篇幅
    fragments = [f for f in _FRAGMENT_SPLIT_RE.split(text) if len(f.strip()) >= 6]
    if not fragments:
        return False
    counts: dict[str, int] = {}
    for frag in fragments:
        key = frag.strip()
        counts[key] = counts.get(key, 0) + 1
    total_len = len(compact)
    for frag, count in counts.items():
        if count >= 5 and len(frag) * count / max(total_len, 1) >= 0.3:
            return True
    return False


def _is_truncated(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if len(_FENCE_RE.findall(stripped)) % 2 == 1:
        return True
    if _DANGLING_END_RE.search(stripped):
        return True
    return False


def _has_language_mismatch(text: str, request_message: str) -> bool:
    # 仅防守"中文提问收到无中文长篇拉丁散文"这一高置信情形
    if not request_message or len(_CJK_RE.findall(request_message)) < 2:
        return False
    stripped = text.strip()
    if len(stripped) < 80 or "```" in stripped:
        return False
    if _CJK_RE.findall(stripped):
        return False
    letters = sum(1 for ch in stripped if ch.isascii() and ch.isalpha())
    nonspace = len("".join(stripped.split()))
    return nonspace > 0 and letters / nonspace >= 0.5


def check_response(text: str | None, request_message: str = "") -> SanityResult:
    """对单条回答做机械健全性检查。确定性、无 LLM、不改写内容。"""
    if _is_empty(text):
        return SanityResult(
            verdict=SanityVerdict.RETRY_ONCE,
            reason="empty",
            error_code=ERROR_CODES["empty"],
            detail="回答为空",
        )
    assert text is not None

    if _has_prompt_leak(text):
        return SanityResult(
            verdict=SanityVerdict.USER_SAFE_ERROR,
            reason="prompt_leak",
            error_code=ERROR_CODES["prompt_leak"],
            detail="回答为含内部提示字段的 JSON，不重试直接降级",
        )
    if _has_heavy_repetition(text):
        return SanityResult(
            verdict=SanityVerdict.RETRY_ONCE,
            reason="heavy_repetition",
            error_code=ERROR_CODES["heavy_repetition"],
            detail="回答存在大量重复片段",
        )
    if _is_truncated(text):
        return SanityResult(
            verdict=SanityVerdict.RETRY_ONCE,
            reason="truncated",
            error_code=ERROR_CODES["truncated"],
            detail="回答疑似截断",
        )
    if _has_language_mismatch(text, request_message):
        return SanityResult(
            verdict=SanityVerdict.RETRY_ONCE,
            reason="language_mismatch",
            error_code=ERROR_CODES["language_mismatch"],
            detail="回答语言与请求明显不一致",
        )
    return SanityResult(verdict=SanityVerdict.ACCEPT, reason="ok", text=text)


async def run_with_sanity_check(
    generate,
    context,
    *,
    request_message: str = "",
    max_attempts: int = 2,
    check=check_response,
) -> SanityOutcome:
    """以相同 BuiltContext 生成并检查，至多重试一次。

    Args:
        generate: async callable(context) -> str，重试时收到完全相同的 context。
        context: 生成所需的上下文（BuiltContext 或等价 dict）。
        request_message: 当前用户消息原文（仅用于语言一致性检查）。
        max_attempts: 最大尝试次数，默认 2（首次 + 一次重试）。

    Returns:
        SanityOutcome。verdict 为 USER_SAFE_ERROR 时 text 恒为 None，
        调用方应将其转为 SSE error 事件，而不是伪造 content。
    """
    failure_reasons: list[str] = []
    attempts = 0
    while attempts < max_attempts:
        attempts += 1
        text = await generate(context)
        result = check(text, request_message)
        if result.verdict is SanityVerdict.ACCEPT:
            return SanityOutcome(
                text=result.text,
                verdict=SanityVerdict.ACCEPT,
                error_code=None,
                attempts=attempts,
                failure_reasons=failure_reasons,
            )
        failure_reasons.append(result.reason)
        if result.verdict is SanityVerdict.USER_SAFE_ERROR:
            return SanityOutcome(
                text=None,
                verdict=SanityVerdict.USER_SAFE_ERROR,
                error_code=result.error_code,
                attempts=attempts,
                failure_reasons=failure_reasons,
            )
    # 重试仍失败：返回可恢复错误与脱敏 error_code
    return SanityOutcome(
        text=None,
        verdict=SanityVerdict.USER_SAFE_ERROR,
        error_code=ERROR_CODES.get(failure_reasons[-1], "GENERATION_FAILED"),
        attempts=attempts,
        failure_reasons=failure_reasons,
    )
