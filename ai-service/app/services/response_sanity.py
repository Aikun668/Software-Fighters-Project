"""ResponseSanityCheck — 输出健全性检查与一次重试（对话底座救援 · Task 8）。

设计约束（设计文档 · ResponseSanityCheck）：
- 第一轮只检查高置信异常：空回答、过度重复、明显截断、内部提示词/JSON 泄露、
  请求语言明显不一致。不做"事实是否正确"的判定。
- 最多以相同 BuiltContext 重试一次；再次失败返回可恢复错误与脱敏 error_code。
- 检查器不得改写正常回答（ACCEPT 时原文返回）。

截断判定刻意保守（避免误伤列表/代码/无句号结尾的正常回答）：
只认未闭合代码围栏、悬空连接标点（，、：；等）与未闭合括号三类强信号。

语言一致性检查只在"用户未指定输出语言"时生效：用户明确要求
"用英文写""输出不要中文"时，回答全英文属于正确履约，不得判为异常。
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

# 高置信内部核查标记（P4 评审 af-01）：这些 QA 管线措辞只应存在于日志，
# 出现在回答正文即为泄露。历史脏数据里带着核查块的旧回答可能被模型模仿，
# 用精确短语拦截，宁可漏过也不用宽泛词（如"仅供参考"）误伤正常回答。
_INTERNAL_MARKERS = (
    "内容核查提示",
    "以下内容置信度较低",
)

# 未闭合代码围栏：``` 出现奇数次
_FENCE_RE = re.compile(r"```")

# 悬空连接标点：句子明显没说完
_DANGLING_END_RE = re.compile(r"[，、：；,;\-（【\[\{]$")

# 终端标点（用于切分重复片段）
_FRAGMENT_SPLIT_RE = re.compile(r"[。！？!?\n；;，,]+")

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

# 用户显式要求外语输出的信号。
#
# 语言一致性检查的前提是「提问语言 = 期望回答语言」，一旦用户明确要求
# 换语言（"用英文写""输出不要中文""translate into English"），该前提就不成立：
# 此时回答全英文是**正确履约**，不是异常。缺失这些豁免会导致
# 「要求英文作文」这类请求被确定性误杀（两轮重试必然同样失败，正文被整体丢弃）。
_LANG_OVERRIDE_RE = re.compile(
    r"(用|以|使用|改为|换成|输出|回答|回复|写|翻译成|翻成)\s*"
    r"(纯\s*)?(英文|英语|中文|汉语|日文|日语|法文|法语|德文|德语|韩文|韩语|西班牙文|西班牙语)"
    r"|(英文|英语|中文|汉语|日文|日语|法文|法语|德文|德语|韩文|韩语)\s*(输出|作答|回复|回答|写作)"
    # 「帮我写一段英文自我介绍」这类动词与语言词被量词隔开的形态
    r"|(写|来|生成|输出|回答|回复)[^。！？\n]{0,8}?(英文|英语|日文|日语|法文|法语|德文|德语)"
    r"|不要(用)?(中文|英文|英语|汉语)"
    r"|(纯|全|只用|仅用)\s*(英文|英语|中文|汉语|日文|日语)"
    r"|in\s+english|in\s+chinese|english\s+only|translate\s+(in)?to\s+english"
    r"|no\s+chinese|only\s+english",
    re.IGNORECASE,
)


def _requests_language_override(request_message: str) -> bool:
    """用户是否在请求里显式指定了输出语言。

    命中时跳过语言一致性检查——回答跟随用户指定的语言即视为正常。
    判定刻意保守：只认明确的语言指令措辞，避免把
    「中文里顺带提到英文术语」这类普通提问误判成换语言要求。
    """
    if not request_message:
        return False
    return bool(_LANG_OVERRIDE_RE.search(request_message))


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


def _has_internal_marker(text: str) -> bool:
    return any(marker in text for marker in _INTERNAL_MARKERS)


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
    # 仅防守"中文提问收到无中文长篇拉丁散文"这一高置信情形。
    # 用户显式指定输出语言时该前提不成立，直接放行（否则"要求英文作文"
    # 会被确定性误杀：重试上下文相同，两轮必然同为英文，正文被整体丢弃）。
    if _requests_language_override(request_message):
        return False
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
    if _has_internal_marker(text):
        return SanityResult(
            verdict=SanityVerdict.USER_SAFE_ERROR,
            reason="prompt_leak",
            error_code=ERROR_CODES["prompt_leak"],
            detail="回答包含内部核查标记，不重试直接降级",
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
