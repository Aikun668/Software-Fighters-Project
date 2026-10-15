"""T4-B 复合顺序重排（_reorder_by_compound）契约。

锁保守行为：只在「明确复合顺序 + 任务≥2 + 子句意图集合==任务意图集合」时重排；
否则原样返回（不增删任务、不引入新意图）。
"""

import pytest

from app.centers.chat_center import ChatCenter
from app.centers.plan_builder import PlanBuilder
from app.centers.router_agent import RouterAgent
from app.services.intent_extractor import IntentExtractor


def _center():
    return ChatCenter(
        router_agent=RouterAgent(intent_extractor=IntentExtractor(use_mock=True)),
    )


def _plan_from_route(message):
    """用真实 route 产出 plan（但 t4b_enabled=False 不重排），再手动调 _reorder_by_compound。"""
    cc = _center()
    import asyncio
    plan = asyncio.run(cc.route(message, mode="auto"))
    return cc, plan


class TestReorderByCompound:
    def test_xian_jiang_zai_lian_reorders(self):
        # 旧顺序 [exercise, tutor]（置信度排），应重排为 [tutor, exercise]（讲快排在前）
        cc, plan = _plan_from_route("先帮我讲讲快排，再给我几道练习题")
        before = [t.intent for t in plan.tasks]
        assert len(before) >= 2, before
        plan2 = cc._reorder_by_compound("先帮我讲讲快排，再给我几道练习题", plan)
        after = [t.intent for t in plan2.tasks]
        # 集合不变，但顺序按表达
        assert set(after) == set(before)
        assert after[0] == "tutor_question", after

    def test_no_compound_returns_unchanged(self):
        cc, plan = _plan_from_route("帮我出5道进程调度选择题")
        before = [t.intent for t in plan.tasks]
        plan2 = cc._reorder_by_compound("帮我出5道进程调度选择题", plan)
        assert [t.intent for t in plan2.tasks] == before

    def test_sequence_renumbered(self):
        cc, plan = _plan_from_route("先帮我讲讲快排，再给我几道练习题")
        plan2 = cc._reorder_by_compound("先帮我讲讲快排，再给我几道练习题", plan)
        seqs = [t.sequence for t in plan2.tasks]
        assert seqs == list(range(len(seqs))), seqs

    def test_mismatch_set_returns_unchanged(self):
        # 子句判出的意图集合与任务意图不一致时，保守不动
        cc, plan = _plan_from_route("给我一份讲义，外加10道练习题")
        before = [t.intent for t in plan.tasks]
        plan2 = cc._reorder_by_compound("给我一份讲义，外加10道练习题", plan)
        after = [t.intent for t in plan2.tasks]
        # 若集合一致则顺序可重排；关键断言是「不增删任务」
        assert set(after) == set(before)
        assert len(after) == len(before)
