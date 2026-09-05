"""CapabilityGate 合同测试（对话底座救援 · Task 4）。

一级路由只允许五种结果，默认 NORMAL_CHAT；
只有"明确动词 + 明确产物"的高置信证据才允许进入能力编排。
"""
import pytest

from app.centers.chat_center import ChatCenter
from app.centers.router_agent import RouterAgent
from app.services.capability_gate import CapabilityDecision, CapabilityGate, CapabilityKind
from app.services.intent_extractor import IntentExtractor


@pytest.fixture
def gate():
    return CapabilityGate()


# ═══════════════════════════════════════════════════════════════
# 计划规定的 5 条合同样例
# ═══════════════════════════════════════════════════════════════

class TestGateContractSamples:
    def test_knowledge_graph_question_is_normal_chat(self, gate):
        d = gate.decide("知识图谱是什么？")
        assert d.kind is CapabilityKind.NORMAL_CHAT

    def test_confused_feeling_is_normal_chat(self, gate):
        d = gate.decide("我感觉 TCP 没学懂，简单讲讲")
        assert d.kind is CapabilityKind.NORMAL_CHAT

    def test_explicit_diagram_request_is_visualization(self, gate):
        d = gate.decide("给我画一张 TCP 三次握手流程图")
        assert d.kind is CapabilityKind.VISUALIZATION

    def test_explicit_exercise_request_is_exercise(self, gate):
        d = gate.decide("帮我出 5 道进程调度选择题")
        assert d.kind is CapabilityKind.EXERCISE

    def test_explicit_plan_request_is_plan(self, gate):
        d = gate.decide("基于本周课程制定 7 天计划")
        assert d.kind is CapabilityKind.PLAN


# ═══════════════════════════════════════════════════════════════
# 保守回退规则
# ═══════════════════════════════════════════════════════════════

class TestGateFallbackRules:
    @pytest.mark.parametrize("message", [
        "举个例子说明一下进程和线程",
        "随便聊聊",
        "你好",
        "这道题怎么做？",
        "帮我做这道题",
        "流程图怎么画？",
        "做了5道题都错了",
        "我找了一天资料都没找到",
    ])
    def test_ambiguous_inputs_fall_back_to_normal_chat(self, gate, message):
        d = gate.decide(message)
        assert d.kind is CapabilityKind.NORMAL_CHAT, f"{message!r} 应回落 NORMAL_CHAT"

    def test_blank_message_is_normal_chat(self, gate):
        assert gate.decide("   ").kind is CapabilityKind.NORMAL_CHAT

    def test_decision_has_reason_and_confidence(self, gate):
        d = gate.decide("帮我出 5 道进程调度选择题")
        assert isinstance(d, CapabilityDecision)
        assert isinstance(d.reason, str) and d.reason
        assert 0.0 <= d.confidence <= 1.0

    def test_normal_chat_reason_mentions_lack_of_evidence(self, gate):
        d = gate.decide("什么是虚拟内存？")
        assert d.kind is CapabilityKind.NORMAL_CHAT
        assert d.reason


# ═══════════════════════════════════════════════════════════════
# 显式 mode 优先
# ═══════════════════════════════════════════════════════════════

class TestGateExplicitMode:
    @pytest.mark.parametrize("mode,kind", [
        ("plan", CapabilityKind.PLAN),
        ("resource", CapabilityKind.RESOURCE),
        ("exercise", CapabilityKind.EXERCISE),
        ("visualization", CapabilityKind.VISUALIZATION),
    ])
    def test_explicit_mode_maps_to_kind(self, gate, mode, kind):
        d = gate.decide("随便什么内容", mode=mode)
        assert d.kind is kind
        assert d.confidence >= 1.0

    def test_auto_mode_is_not_explicit(self, gate):
        d = gate.decide("帮我出 5 道题", mode="auto")
        assert d.kind is CapabilityKind.EXERCISE
        assert d.confidence < 1.0


# ═══════════════════════════════════════════════════════════════
# ChatCenter 接线：NORMAL_CHAT 直达 TutorAgent，能力请求才进 RouterAgent
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def chat_center():
    return ChatCenter(
        router_agent=RouterAgent(intent_extractor=IntentExtractor(use_mock=True)),
    )


class TestChatCenterGateWiring:
    @pytest.mark.asyncio
    async def test_normal_chat_yields_single_tutor_task(self, chat_center):
        plan = await chat_center.route("什么是进程？", mode="auto")
        assert len(plan.tasks) == 1
        assert plan.tasks[0].mode == "auto"
        assert plan.tasks[0].intent == "tutor_question"
        assert plan.intent_meta.get("strategy") == "capability_gate"
        assert plan.intent_meta.get("route") == "NORMAL_CHAT"

    @pytest.mark.asyncio
    async def test_normal_chat_never_creates_complex_plan(self, chat_center):
        plan = await chat_center.route("我感觉 TCP 没学懂，简单讲讲", mode="auto")
        assert len(plan.tasks) == 1
        assert plan.tasks[0].mode == "auto"

    @pytest.mark.asyncio
    async def test_capability_request_still_reaches_router(self, chat_center):
        plan = await chat_center.route(
            "帮我规划Python学习路径，安排学习计划，再出5道练习题", mode="auto"
        )
        assert len(plan.tasks) >= 2
        modes = {t.mode for t in plan.tasks}
        assert "plan" in modes
        assert "exercise" in modes

    @pytest.mark.asyncio
    async def test_explicit_mode_passes_through(self, chat_center):
        plan = await chat_center.route("练习内容", mode="exercise")
        assert plan.tasks[0].mode == "exercise"

    @pytest.mark.asyncio
    async def test_blank_message_becomes_inquiry(self, chat_center):
        plan = await chat_center.route("   ", mode="auto")
        assert plan.is_clear is False
        assert plan.tasks[0].mode == "inquiry"
