"""T4-A 契约：三态判定 / 预算 / 旁路不改执行。

锁定五件事：
  1. 三态判定本身确定性、无 LLM（classify 是纯函数）
  2. 明确能力 → DIRECT_CAPABILITY（不调语义）
  3. 明确聊天 → DIRECT_CHAT（不调语义）
  4. 不确定 → UNCERTAIN，且语义调用有超时预算、异常兜底不抛
  5. 旁路模式不改实际路由（由 ChatCenter 契约另行锁定）

预算铁律（每请求 ≤1 次语义调用）在这里锁「classify 不触发调用、semantic_relabel 只调一次
且受 asyncio.timeout 约束」；「ChatCenter 只在 UNCERTAIN 态调一次」由 test_t4a_chatcenter
另测。
"""

import asyncio

import pytest

from app.services.semantic_router import (
    RouteState,
    classify,
    semantic_relabel,
)


# ── 三态判定（纯函数）───────────────────────────────────────────


class TestClassifyThreeStates:
    def test_capability_evidence_is_direct_capability(self):
        d = classify(
            gate_kind="EXERCISE",
            gate_reason="capability_evidence:verb_count_exercise",
            gate_confidence=0.75,
            message="出5道题",
        )
        assert d.state is RouteState.DIRECT_CAPABILITY
        assert d.semantic_called is False

    def test_explicit_mode_is_direct_capability(self):
        d = classify(
            gate_kind="PLAN",
            gate_reason="explicit_mode:plan",
            gate_confidence=1.0,
            message="随便安排点东西",
        )
        assert d.state is RouteState.DIRECT_CAPABILITY

    def test_question_mark_is_direct_chat(self):
        d = classify(
            gate_kind="NORMAL_CHAT",
            gate_reason="no_capability_evidence",
            gate_confidence=0.5,
            message="什么是进程调度",
        )
        assert d.state is RouteState.DIRECT_CHAT
        assert d.semantic_called is False

    def test_negation_is_direct_chat(self):
        d = classify(
            gate_kind="NORMAL_CHAT",
            gate_reason="no_capability_evidence",
            gate_confidence=0.5,
            message="不要出题，只要讲解",
        )
        assert d.state is RouteState.DIRECT_CHAT

    def test_vague_no_evidence_is_uncertain(self):
        # 「数据好难」既无能力证据、也不是明确疑问/否定 → 不得默认答疑
        d = classify(
            gate_kind="NORMAL_CHAT",
            gate_reason="no_capability_evidence",
            gate_confidence=0.5,
            message="数据结构好难啊",
        )
        assert d.state is RouteState.UNCERTAIN

    def test_question_over_capability_is_uncertain(self):
        # 疑问句式压制了能力证据 → 复合/边界诉求，走语义
        d = classify(
            gate_kind="NORMAL_CHAT",
            gate_reason="question_over_capability:verb_count_exercise",
            gate_confidence=0.6,
            message="先讲解进程，再出5道题",
        )
        assert d.state is RouteState.UNCERTAIN

    def test_unknown_mode_is_uncertain(self):
        d = classify(
            gate_kind="NORMAL_CHAT",
            gate_reason="unknown_mode:foo",
            gate_confidence=0.5,
            message="whatever",
        )
        assert d.state is RouteState.UNCERTAIN


class TestNegationAndQuoting:
    """否定/引用优先于能力证据：不得直通能力（B1 否定识别）。"""

    def test_negated_capability_is_direct_chat(self):
        # gate 因"出题"命中 EXERCISE，但用户明确"不要" → 不得直通能力
        d = classify(
            gate_kind="EXERCISE",
            gate_reason="capability_evidence:verb_topic_exercise",
            gate_confidence=0.75,
            message="不要给我出题，我只要讲解",
        )
        assert d.state is RouteState.DIRECT_CHAT

    def test_negated_diagram_is_direct_chat(self):
        d = classify(
            gate_kind="VISUALIZATION",
            gate_reason="capability_evidence:draw_diagram",
            gate_confidence=0.75,
            message="不用画图，文字说明就行",
        )
        assert d.state is RouteState.DIRECT_CHAT

    def test_quoted_capability_is_direct_chat(self):
        # 「出题」被引号包裹，是转述（老师布置的作业），不是诉求
        d = classify(
            gate_kind="EXERCISE",
            gate_reason="capability_evidence:verb_topic_exercise",
            gate_confidence=0.75,
            message="刚才题目里说的「出题」是老师布置的作业",
        )
        assert d.state is RouteState.DIRECT_CHAT

    def test_plain_capability_still_direct_capability(self):
        # 无否定/引号的能力请求必须仍然直通
        d = classify(
            gate_kind="EXERCISE",
            gate_reason="capability_evidence:verb_count_exercise",
            gate_confidence=0.75,
            message="帮我出5道进程调度选择题",
        )
        assert d.state is RouteState.DIRECT_CAPABILITY


# ── 语义重判：预算 + 兜底 ────────────────────────────────────────


class _SlowExtractor:
    """mock IntentExtractor：可注入挂起/异常，验证超时与兜底。

    注意：不能依赖 `asyncio.sleep` —— conftest 的 autouse `mock_sleep` 会把它
    patch 成立即返回，导致超时永不触发。这里用永不完成的 `asyncio.Future()`
    来模拟「模型挂起」，`asyncio.timeout` 仍会按真实墙钟超时。
    """

    def __init__(self, hang=False, raise_exc=None, result=None):
        self.hang = hang
        self.raise_exc = raise_exc
        self.result = result
        self.calls = 0

    async def extract_multi(self, message, max_intents=3, clarity_threshold=0.5):
        self.calls += 1
        if self.hang:
            await asyncio.Future()  # 永不完成 → 触发 asyncio.timeout
        if self.raise_exc:
            raise self.raise_exc
        if self.result is not None:
            return self.result
        from app.services.intent_extractor import IntentResult, MultiIntentResult

        return MultiIntentResult(
            intents=[IntentResult(intent="tutor_question", confidence=0.5)],
            is_clear=True,
            raw_message=message,
        )


class TestSemanticRelabelBudget:
    @pytest.mark.asyncio
    async def test_success_returns_intents_and_latency(self):
        intents, confidences, is_clear, inquiry, latency, err = await semantic_relabel(
            message="数据好难", intent_extractor=_SlowExtractor()
        )
        assert intents == ["tutor_question"]
        assert confidences == [0.5]
        assert is_clear is True
        assert latency is not None and latency >= 0
        assert err is None

    @pytest.mark.asyncio
    async def test_timeout_falls_back_without_raising(self):
        intents, confidences, is_clear, inquiry, latency, err = await semantic_relabel(
            message="数据好难",
            intent_extractor=_SlowExtractor(hang=True),
        )
        assert intents == []
        assert confidences == []
        assert err == "timeout"

    @pytest.mark.asyncio
    async def test_exception_falls_back_without_raising(self):
        intents, confidences, is_clear, inquiry, latency, err = await semantic_relabel(
            message="数据好难",
            intent_extractor=_SlowExtractor(raise_exc=RuntimeError("boom")),
        )
        assert intents == []
        assert confidences == []
        assert err == "RuntimeError"

    @pytest.mark.asyncio
    async def test_single_call_only(self):
        ex = _SlowExtractor()
        await semantic_relabel(message="x", intent_extractor=ex)
        assert ex.calls == 1
