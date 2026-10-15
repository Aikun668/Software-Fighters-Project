"""三态语义路由（T4-A）：把「明确聊天 / 明确能力 / 不确定」分开，只让第三态按需调用语义判定。

【决策所有权】三态边界的唯一裁决点 —— 由 `ChatCenter.route` 调用，本模块不 import
  `CapabilityGate` / `RouterAgent` / `PlanBuilder`（所有权契约约束），只接收已产出的
  一级 gate 结论（kind/reason/confidence 三个裸值）作为输入，输出三态判定与可选语义重判。

职责：
  - DIRECT_CAPABILITY：gate 已命中能力规则且未被疑问句式压制 → 直通（不调 LLM）
  - DIRECT_CHAT：无能力证据但明确是「答疑/否定/寒暄/引用」→ 直通 NORMAL_CHAT（不调 LLM）
  - UNCERTAIN：其余 → 按需调用 `IntentExtractor.extract_multi` 做语义重判

安全铁律（预算，T4-A-Gate）：
  - 每请求最多 1 次语义调用，仅 UNCERTAIN 态触发
  - 语义调用 `asyncio.timeout(SEMANTIC_TIMEOUT_SEC)` 包裹，超时/异常/非法输出 → 兜底为原行为
  - 语义结果必须由调用方（ChatCenter）交 `PlanBuilder` 校验后才可执行，本模块不直接造产物
  - 旁路模式（`enabled=False`）：只返回判定与审计字段，不改变执行；由 ChatCenter 决定是否采纳

【命名澄清】不是 LLM Agent，是纯判定服务：三态判定本身确定性、无 LLM；只有 UNCERTAIN 态
  才委托 IntentExtractor 做一次按需语义判定。改名不适用，本模块为 T4-A 新增。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# 语义调用的超时预算。真模型实测 p95≈1506ms、max≈1506ms（见 T4-A-handoff 第十节），
# 按产品决定放宽到 1.5s：p95 基本落在预算内，同时仍以「超时即兜底」保底，
# 避免慢请求无限占用热路径。
SEMANTIC_TIMEOUT_SEC = 1.5

# 启用接管的最小置信度：语义腿给唯一能力意图时，最高置信度低于此值不接管，
# 保持旧行为（答疑兜底）。设 0.6 是因为 mock 关键词腿把单命中换算成 0.597 的
# 伪置信度（"举个例子"→resource 即此），0.6 能把这类低置信误判挡在门外；
# 真 LLM 腿给明确能力通常 ≥0.8，能正常过门槛。此值可在预算实测阶段按真模型分布回调。
SEMANTIC_TAKEOVER_CONFIDENCE = 0.6


class RouteState(str, Enum):
    """三态：直通能力 / 直通聊天 / 不确定（需语义重判）。"""

    DIRECT_CAPABILITY = "direct_capability"
    DIRECT_CHAT = "direct_chat"
    UNCERTAIN = "uncertain"


@dataclass
class SemanticDecision:
    """三态判定 + 语义重判结果 + 审计元数据。纯数据，无业务 import。"""

    state: RouteState
    # gate 原始判定（透传，供审计可回溯）
    gate_kind: str
    gate_reason: str
    gate_confidence: float
    # 语义重判结果（仅 UNCERTAIN 态填充；其余为空）
    semantic_called: bool = False
    intents: list[str] = field(default_factory=list)
    is_clear: bool = True
    inquiry_question: str = ""
    # 审计：语义调用时延与错误
    semantic_latency_ms: float | None = None
    semantic_error: str | None = None


def classify(
    *,
    gate_kind: str,
    gate_reason: str,
    gate_confidence: float,
    message: str,
) -> SemanticDecision:
    """确定性三态判定（同步、无 LLM）。

    判据：
      - gate 命中能力（capability_evidence:* / explicit_mode:*）且未被 question_over_capability
        压制 → DIRECT_CAPABILITY
      - 无能力证据（no_capability_evidence / empty_message）且明确是答疑/否定/寒暄 → DIRECT_CHAT
      - 其余（question_over_capability 压制、unknown_mode、或 no_capability_evidence 但非明确聊天）
        → UNCERTAIN
    """
    # 明确否定 / 引用转述优先于能力证据：即使 gate 因能力词命中，
    # 用户说「不要出题」「不用画图」「题目里说的『出题』是作业」时，
    # 也不能直通能力（T4-A 第 1 条 + B1 否定识别）。
    if gate_reason.startswith("capability_evidence:") and _is_negated_or_quoted(message):
        return SemanticDecision(
            state=RouteState.DIRECT_CHAT,
            gate_kind=gate_kind,
            gate_reason=gate_reason,
            gate_confidence=gate_confidence,
        )

    # T4-B：明确复合表达（"先讲再练""讲义外加题"）即使 gate 命中能力，也判 UNCERTAIN，
    # 让语义腿返回多意图、按表达顺序建多任务，避免第二诉求被吞。确定性规则，不加 LLM。
    if detect_compound_order(message):
        return SemanticDecision(
            state=RouteState.UNCERTAIN,
            gate_kind=gate_kind,
            gate_reason=gate_reason,
            gate_confidence=gate_confidence,
        )

    if gate_reason.startswith("capability_evidence:") or gate_reason.startswith(
        "explicit_mode:"
    ):
        return SemanticDecision(
            state=RouteState.DIRECT_CAPABILITY,
            gate_kind=gate_kind,
            gate_reason=gate_reason,
            gate_confidence=gate_confidence,
        )

    # 疑问句式压制了能力证据：需要更细的判定（可能是"讲解+出题"复合诉求，或单纯答疑）
    if gate_reason.startswith("question_over_capability"):
        return SemanticDecision(
            state=RouteState.UNCERTAIN,
            gate_kind=gate_kind,
            gate_reason=gate_reason,
            gate_confidence=gate_confidence,
        )

    # 未知显式 mode：不在五态能力枚举内，需语义重判
    if gate_reason == "unknown_mode":
        return SemanticDecision(
            state=RouteState.UNCERTAIN,
            gate_kind=gate_kind,
            gate_reason=gate_reason,
            gate_confidence=gate_confidence,
        )

    # 以下 reason：no_capability_evidence / empty_message —— 需区分「明确聊天」与「不确定」
    if _is_clearly_chat(message):
        return SemanticDecision(
            state=RouteState.DIRECT_CHAT,
            gate_kind=gate_kind,
            gate_reason=gate_reason,
            gate_confidence=gate_confidence,
        )

    return SemanticDecision(
        state=RouteState.UNCERTAIN,
        gate_kind=gate_kind,
        gate_reason=gate_reason,
        gate_confidence=gate_confidence,
    )


def _is_negated_or_quoted(message: str) -> bool:
    """「明确否定能力诉求」或「能力词被引用转述」的规则判据（确定性）。

    - 明确否定：含否定词且句中同时出现能力意图的典型祈使（如"不要给我出题"）。
      只认最强否定词（不要/不用/别/不需要/不想/并非），避免误伤"要不要出题"这类真询问。
    - 引用转述：能力词被中文引号包裹（「出题」/“出题”/‘出题’），属转述而非诉求。
    """
    text = message.strip()
    if not text:
        return False
    negations = ("不要", "不用", "别", "不需要", "不想", "并非")
    if any(n in text for n in negations):
        return True
    # 引号包裹的能力词（含全角「」“”‘’与半角引号）
    import re as _re

    if _re.search(r"[「“”‘’\"']\S{1,6}[」“”‘’\"']", text):
        return True
    return False


def _is_clearly_chat(message: str) -> bool:
    """「明确普通聊天」的规则判据（确定性、无 LLM）。

    只把"确定无疑属于答疑/寒暄/否定/引用"的输入判为明确聊天；其余一律不确定，
    宁可多走语义判定，也不把「没命中关键词」直接等同于「明确普通聊天」（T4-A 第 2 条）。
    """
    text = message.strip()
    if not text:
        return False  # 空输入交 empty_message 分支，不在这里判

    # 疑问句式：明确的答疑/概念提问
    _QUESTION_MARKS = (
        "什么", "为什么", "怎么", "如何", "是什么", "何为", "区别", "区别是",
        "讲讲", "讲解", "解释", "介绍一下", "说说", "分析", "举例",
    )
    if any(m in text for m in _QUESTION_MARKS):
        return True

    # 明确否定 + 引用/转述（否定表达、引用内容干扰 → 应回落答疑，不触发能力）
    _NEGATION_MARKS = ("不要", "不用", "别", "不是问", "不需要", "不想")
    if any(m in text for m in _NEGATION_MARKS):
        return True

    # 纯寒暄 / 无信息
    _GREETINGS = ("你好", "在吗", "嗯", "谢谢", "再见", "好的", "行", "可以")
    if text in _GREETINGS or len(text) <= 1:
        return True

    return False


async def semantic_relabel(
    *,
    message: str,
    intent_extractor: Any | None = None,
    max_intents: int = 3,
    clarity_threshold: float = 0.5,
) -> tuple[list[str], list[float], bool, str, float | None, str | None]:
    """按需语义重判：委托 IntentExtractor.extract_multi，超时/异常兜底。

    返回 (intents, confidences, is_clear, inquiry_question, latency_ms, error)。
    confidences 与 intents 同序，供接管方设置信度门槛；失败时为空列表。
    超时/失败时不抛异常，返回空列表让调用方兜底为原行为。
    """
    from app.services.intent_extractor import IntentExtractor  # noqa: E402 延迟导入，避免契约依赖

    extractor = intent_extractor or IntentExtractor()
    started = time.perf_counter()
    try:
        async with asyncio.timeout(SEMANTIC_TIMEOUT_SEC):
            result = await extractor.extract_multi(
                message, max_intents=max_intents, clarity_threshold=clarity_threshold
            )
        latency_ms = (time.perf_counter() - started) * 1000
        intents = [r.intent for r in result.intents]
        confidences = [r.confidence for r in result.intents]
        return (
            intents,
            confidences,
            result.is_clear,
            result.inquiry_question,
            latency_ms,
            None,
        )
    except TimeoutError:
        return ([], [], True, "", (time.perf_counter() - started) * 1000, "timeout")
    except Exception as exc:  # 模型不可用 / 输出非法 → 兜底
        logger.warning("semantic_relabel failed: %s", exc)
        return ([], [], True, "", (time.perf_counter() - started) * 1000, type(exc).__name__)


# ── T4-B：复合表达识别 ────────────────────────────────────────────

# 明确的复合连接词（按「用户表达顺序」切分）。只认这些强连接词，避免误切普通句子。
# "先 X 再 Y" 的「先」用前瞻式短语单独处理（见 _split_compound）。
_COMPOUND_CONNECTORS = (
    "然后", "接着", "之后", "再给我", "顺便", "外加", "再加上", "并且",
    "以及", "然后帮我", "然后给我",
)

# 「再 + 祈使动词」也是复合连接（"再制定/再画/再出/再做/再找"），
# 但要排除"再来5道/再看一眼"这类跨轮指代（"来/看"非祈使动词）。
_COMPOUND_RE_VERBS = (
    "制定", "规划", "画", "绘制", "出", "做", "找", "生成", "安排",
    "加", "整理", "推荐", "设计", "讲", "解释", "出几道", "给",
)


def detect_compound_order(message: str) -> list[str] | None:
    """识别一句里的多个诉求，返回按**用户表达顺序**的子句列表。

    只认明确的复合连接词（"先讲解再出题""帮我找资料，再制定计划""出5道题顺便做图谱"）。
    识别不到明确复合结构时返回 None（交给现有单意图/多候选路径）。

    确定性、无 LLM；仅供 plan_builder 作排序参考，本函数不改变任何路由结果。
    """
    if not message or not message.strip():
        return None

    def _clean(s: str) -> str:
        return s.strip().strip("，,。.；;！!？? ")

    text = message.strip()

    # 1) "先 ... 再/然后 ..." 结构
    if text.startswith("先") or "先" in text[:4]:
        stripped = text.lstrip("先").lstrip("，, ")
        for cut in ("再", "然后"):
            if cut in stripped:
                first, second = stripped.split(cut, 1)
                first, second = _clean(first), _clean(second)
                if first and second:
                    return [first, second]
                break

    # 2) 通用复合连接词切分
    for conn in _COMPOUND_CONNECTORS:
        if conn in text:
            first, second = text.split(conn, 1)
            first, second = _clean(first), _clean(second)
            if first and second:
                return [first, second]

    # 3) 「再 + 祈使动词」："帮我找资料，再制定一个计划" → ["帮我找资料","制定一个计划"]
    import re as _re
    m = _re.search(r"[，,。；;]?\s*再(?=(?:" + "|".join(_COMPOUND_RE_VERBS) + r"))", text)
    if m and m.start() > 0:
        first = _clean(text[:m.start()])
        second = _clean(text[m.end():])
        if first and second:
            return [first, second]

    return None
