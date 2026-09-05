"""路由观测与脱敏审计测试（对话底座救援 · Task 5）。

每次聊天请求在 ChatCenter 边界产出一条结构化、脱敏的路由日志：
trace_id、conversation_id、route、route_reason、context_turn_count、
model_latency_ms、retry_count、sse_terminal_event。

红线：日志不得包含 student_profile 全量内容、历史消息正文或回答正文。
"""
import json

import pytest

from app.centers.chat_center import ChatCenter
from app.centers.router_agent import RouterAgent
from app.events.types import content_event, done_event
from app.services.intent_extractor import IntentExtractor
from app.services.routing_audit import ALLOWED_KEYS, AUDIT_LOGGER

# 便于断言"不得出现"的哨兵值：画像值、历史正文、回答正文
_PROFILE_SENTINEL = "绝密画像值-学习目标XYZ"
_HISTORY_USER_SENTINEL = "历史正文-用户消息ABC"
_HISTORY_ASSISTANT_SENTINEL = "历史正文-助手回复DEF"
_ANSWER_SENTINEL = "回答正文-不应进日志"


class _FakeResultAgent:
    """替代 ResultAgent：按脚本吐事件，保持 execute 路径离线可测。"""

    def __init__(self, events=None, raise_exc=None):
        self._events = events or [content_event({"content": _ANSWER_SENTINEL}), done_event({"results": []})]
        self._raise = raise_exc

    async def execute(self, plan):
        for event in self._events:
            if self._raise is not None:
                raise self._raise
            yield event


@pytest.fixture
def chat_center():
    return ChatCenter(
        router_agent=RouterAgent(intent_extractor=IntentExtractor(use_mock=True)),
        result_agent=_FakeResultAgent(),
    )


def _audit_records(caplog):
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == AUDIT_LOGGER]


def _student_profile():
    return {
        "learning_goal": _PROFILE_SENTINEL,
        "weak_points": ["数学基础", "Python"],
        "cognitive_style": "visual",
    }


def _history():
    return [
        {"role": "user", "content": _HISTORY_USER_SENTINEL},
        {"role": "assistant", "content": _HISTORY_ASSISTANT_SENTINEL},
    ]


# ═══════════════════════════════════════════════════════════════
# 计划要求的失败测试：日志包含 route=NORMAL_CHAT；不泄露画像/历史
# ═══════════════════════════════════════════════════════════════

class TestRoutingAuditLog:
    @pytest.mark.asyncio
    async def test_normal_chat_logs_route_and_no_privacy(self, chat_center, caplog):
        caplog.set_level("INFO", logger=AUDIT_LOGGER)
        plan = await chat_center.route(
            "什么是进程？",
            mode="auto",
            student_profile=_student_profile(),
            context={
                "messages": _history(),
                "conversation_id": 7,
                "trace_id": "trace-abc-123",
            },
        )
        async for _ in chat_center.execute(plan):
            pass

        records = _audit_records(caplog)
        assert len(records) == 1
        rec = records[0]

        # 计划要求的核心字段
        assert rec["route"] == "NORMAL_CHAT"
        assert rec["route_reason"]
        assert rec["trace_id"] == "trace-abc-123"
        assert rec["conversation_id"] == 7
        assert rec["context_turn_count"] == 2
        assert isinstance(rec["model_latency_ms"], (int, float)) and rec["model_latency_ms"] >= 0
        assert rec["retry_count"] == 0
        assert rec["sse_terminal_event"] == "done"

        # 白名单之外不允许有任何字段
        assert set(rec.keys()) <= ALLOWED_KEYS

        # 脱敏红线：画像值、历史正文、回答正文一律不出现
        raw = "\n".join(r.getMessage() for r in caplog.records if r.name == AUDIT_LOGGER)
        assert _PROFILE_SENTINEL not in raw
        assert _HISTORY_USER_SENTINEL not in raw
        assert _HISTORY_ASSISTANT_SENTINEL not in raw
        assert _ANSWER_SENTINEL not in raw

    @pytest.mark.asyncio
    async def test_trace_id_generated_when_missing(self, chat_center, caplog):
        caplog.set_level("INFO", logger=AUDIT_LOGGER)
        plan = await chat_center.route("什么是进程？", mode="auto", context={})
        async for _ in chat_center.execute(plan):
            pass
        rec = _audit_records(caplog)[0]
        assert rec["trace_id"]  # 未透传时自动生成，保证可关联

    @pytest.mark.asyncio
    async def test_capability_request_logs_capability_route(self, chat_center, caplog):
        caplog.set_level("INFO", logger=AUDIT_LOGGER)
        plan = await chat_center.route("帮我出 5 道进程调度选择题", mode="auto", context={})
        async for _ in chat_center.execute(plan):
            pass
        rec = _audit_records(caplog)[0]
        assert rec["route"] == "EXERCISE"
        assert rec["sse_terminal_event"] == "done"

    @pytest.mark.asyncio
    async def test_pipeline_exception_logs_error_terminal(self, chat_center, caplog):
        caplog.set_level("INFO", logger=AUDIT_LOGGER)
        cc = ChatCenter(
            router_agent=RouterAgent(intent_extractor=IntentExtractor(use_mock=True)),
            result_agent=_FakeResultAgent(raise_exc=RuntimeError("boom")),
        )
        plan = await cc.route("什么是进程？", mode="auto", context={})
        with pytest.raises(RuntimeError):
            async for _ in cc.execute(plan):
                pass
        rec = _audit_records(caplog)[0]
        assert rec["sse_terminal_event"] == "error"

    @pytest.mark.asyncio
    async def test_plan_without_route_meta_emits_nothing(self, chat_center, caplog):
        """外部直接构造的 plan（如单测）不产生审计日志，也不报错。"""
        caplog.set_level("INFO", logger=AUDIT_LOGGER)
        from app.centers.schemas import CenterTask, ExecutionPlan

        bare = ExecutionPlan(
            tasks=[CenterTask(mode="auto", intent="tutor_question", input="x")],
        )
        async for _ in chat_center.execute(bare):
            pass
        assert _audit_records(caplog) == []


# ═══════════════════════════════════════════════════════════════
# 20 条样例路由正确性（普通问答 12 / 上下文追问 4 / 明确能力 4）
# ═══════════════════════════════════════════════════════════════

AUDIT_SAMPLES = [
    # ── 普通问答 12：期望 NORMAL_CHAT ──
    ("什么是进程？", "NORMAL_CHAT"),
    ("为什么TCP需要三次握手？", "NORMAL_CHAT"),
    ("讲讲虚拟内存的作用", "NORMAL_CHAT"),
    ("操作系统和数据库有什么区别？", "NORMAL_CHAT"),
    ("我感觉TCP一直没搞懂", "NORMAL_CHAT"),
    ("这个再讲简单一点", "NORMAL_CHAT"),
    ("你刚才那个例子我没听明白", "NORMAL_CHAT"),
    ("举个例子说明一下进程和线程", "NORMAL_CHAT"),
    ("二叉树的中序遍历是什么？", "NORMAL_CHAT"),
    ("帮我理解一下递归", "NORMAL_CHAT"),
    ("什么是知识图谱？", "NORMAL_CHAT"),
    ("Python 的 GIL 是什么？", "NORMAL_CHAT"),
    # ── 上下文追问 4：期望 NORMAL_CHAT ──
    ("那线程呢？", "NORMAL_CHAT"),
    ("为什么？", "NORMAL_CHAT"),
    ("不对，我说的是虚拟内存", "NORMAL_CHAT"),
    ("那这个机制在Windows上也一样吗？", "NORMAL_CHAT"),
    # ── 明确能力请求 4 ──
    ("帮我出 5 道进程调度选择题", "EXERCISE"),
    ("给我画一张 TCP 三次握手流程图", "VISUALIZATION"),
    ("基于本周课程制定 7 天计划", "PLAN"),
    ("帮我找几个操作系统的学习资源", "RESOURCE"),
]


class TestTwentySampleRoutingAudit:
    @pytest.mark.parametrize("message,expected", AUDIT_SAMPLES, ids=[s[0] for s in AUDIT_SAMPLES])
    @pytest.mark.asyncio
    async def test_route_matches_expected(self, chat_center, message, expected):
        from app.services.capability_gate import CapabilityKind

        plan = await chat_center.route(
            message,
            mode="auto",
            student_profile=_student_profile(),
            context={"messages": _history()},
        )
        actual = plan.intent_meta.get("route")
        assert actual == expected, f"{message!r} 路由 {actual} != 期望 {expected}"
        if expected == "NORMAL_CHAT":
            assert len(plan.tasks) == 1, "普通问答不得创建复杂 ExecutionPlan"
