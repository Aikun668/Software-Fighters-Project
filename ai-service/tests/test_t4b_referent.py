"""T4-B 跨轮指代消解（_referent_plan / detect_referent）契约。"""

import pytest

from app.centers.chat_center import ChatCenter
from app.centers.router_agent import RouterAgent
from app.services.intent_extractor import IntentExtractor
from app.services.semantic_router import detect_referent


def _center(enabled=True):
    return ChatCenter(
        router_agent=RouterAgent(intent_extractor=IntentExtractor(use_mock=True)),
        t4b_enabled=enabled,
    )


def _ctx(history, message):
    msgs = list(history) + [{"role": "user", "content": message}]
    return {"messages": msgs, "style": "standard", "images": [], "user_id": 0, "conversation_id": None}


class TestDetectReferent:
    def test_referent_marks(self):
        assert detect_referent("再来5道") is True
        assert detect_referent("能不能画得更详细一点") is True
        assert detect_referent("把时间改成两周吧") is True
        assert detect_referent("难度调高一点") is True

    def test_non_referent(self):
        assert detect_referent("帮我出5道进程调度选择题") is False
        assert detect_referent("什么是进程调度") is False
        assert detect_referent("") is False


class TestReferentPlan:
    def test_reuses_prev_exercise(self):
        cc = _center()
        hist = [
            {"role": "user", "content": "帮我出几道二叉树的基础题"},
            {"role": "assistant", "content": "这是5道题……"},
        ]
        plan = cc._referent_plan("再来5道", _ctx(hist, "再来5道"), None, 3)
        assert plan is not None
        assert [t.intent for t in plan.tasks] == ["exercise_gen"]

    def test_reuses_prev_visualize(self):
        cc = _center()
        hist = [
            {"role": "user", "content": "画一张TCP三次握手的流程图"},
            {"role": "assistant", "content": "已生成……"},
        ]
        msg = "能不能画得更详细一点"
        plan = cc._referent_plan(msg, _ctx(hist, msg), None, 3)
        assert plan is not None
        assert [t.intent for t in plan.tasks] == ["visualize"]

    def test_no_history_returns_none(self):
        cc = _center()
        assert cc._referent_plan("再来5道", _ctx([], "再来5道"), None, 3) is None

    def test_prev_tutor_returns_none(self):
        cc = _center()
        hist = [
            {"role": "user", "content": "什么是进程调度"},
            {"role": "assistant", "content": "进程调度是……"},
        ]
        # 上轮是答疑，指代"再讲讲"不该复用成能力
        assert cc._referent_plan("再讲讲", _ctx(hist, "再讲讲"), None, 3) is None

    def test_disabled_returns_none(self):
        cc = _center(enabled=False)
        hist = [
            {"role": "user", "content": "帮我出几道二叉树的基础题"},
            {"role": "assistant", "content": "这是5道题……"},
        ]
        assert cc._referent_plan("再来5道", _ctx(hist, "再来5道"), None, 3) is None
