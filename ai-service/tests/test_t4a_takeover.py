"""T4-A 启用接管的契约：默认 off 不改执行；on 时仅保守接管。

锁定：
  1. 默认 t4a_enabled=False：即使语义给出单一明确能力，也走旧 NORMAL_CHAT（不接管）
  2. on + 语义给出唯一非答疑能力意图 → 接管为对应 center
  3. on + 语义给出 tutor_question → 不接管
  4. on + 多意图 → 不接管
  5. on + 语义出错 → 不接管
  6. on 且 gate 已命中能力（DIRECT_CAPABILITY）→ 不额外接管（保持 gate 权威）
"""

import pytest

from app.centers.chat_center import ChatCenter
from app.centers.router_agent import RouterAgent
from app.services.intent_extractor import IntentExtractor, IntentResult, MultiIntentResult


class _StubExtractor:
    """可控语义结果：注入 intents / is_clear / error，验证接管边界。"""

    def __init__(self, intents, is_clear=True, error=None):
        self.intents = intents
        self.is_clear = is_clear
        self.error = error
        self.calls = 0

    async def extract_multi(self, message, max_intents=3, clarity_threshold=0.5):
        self.calls += 1
        if self.error:
            raise RuntimeError(self.error)
        return MultiIntentResult(
            intents=[IntentResult(intent=i, confidence=0.9) for i in self.intents],
            is_clear=self.is_clear,
            raw_message=message,
        )


def _center(enabled, intents, is_clear=True, error=None):
    return ChatCenter(
        router_agent=RouterAgent(intent_extractor=IntentExtractor(use_mock=True)),
        t4a_enabled=enabled,
        semantic_extractor=_StubExtractor(intents, is_clear=is_clear, error=error),
    )


class TestTakeoverDisabledByDefault:
    """默认 off：语义结果只进审计，绝不接管。"""

    @pytest.mark.asyncio
    async def test_uncertain_with_clear_capability_still_normal_chat(self):
        # "数据好难"：gate 判 NORMAL_CHAT、非疑问/否定/寒暄 → UNCERTAIN；
        # 注入的语义结果强行给 exercise_gen，但默认 off 必须不接管。
        cc = _center(False, ["exercise_gen"])
        plan = await cc.route("数据结构好难啊", mode="auto")
        assert plan.intent_meta.get("semantic_state") == "uncertain"
        # 不接管：仍是 tutor_question 单任务
        assert [t.intent for t in plan.tasks] == ["tutor_question"]
        assert plan.intent_meta.get("route") == "NORMAL_CHAT"


class TestTakeoverConservative:
    """on：仅「单一、非答疑、合法中心」的能力意图才接管。"""

    @pytest.mark.asyncio
    async def test_single_clear_capability_takes_over(self):
        cc = _center(True, ["exercise_gen"])
        plan = await cc.route("数据结构好难啊", mode="auto")
        assert [t.mode for t in plan.tasks] == ["exercise"]

    @pytest.mark.asyncio
    async def test_tutor_question_does_not_take_over(self):
        cc = _center(True, ["tutor_question"])
        plan = await cc.route("数据结构好难啊", mode="auto")
        assert [t.intent for t in plan.tasks] == ["tutor_question"]

    @pytest.mark.asyncio
    async def test_multi_intent_does_not_take_over(self):
        cc = _center(True, ["learning_path", "resource_gen"])
        plan = await cc.route("数据结构好难啊", mode="auto")
        # 多意图：不接管，保持答疑兜底
        assert [t.intent for t in plan.tasks] == ["tutor_question"]

    @pytest.mark.asyncio
    async def test_semantic_error_does_not_take_over(self):
        cc = _center(True, ["exercise_gen"], error="boom")
        plan = await cc.route("数据结构好难啊", mode="auto")
        assert [t.intent for t in plan.tasks] == ["tutor_question"]
        assert plan.intent_meta.get("route_source") == "fallback"

    @pytest.mark.asyncio
    async def test_not_clear_does_not_take_over(self):
        cc = _center(True, ["exercise_gen"], is_clear=False)
        plan = await cc.route("数据结构好难啊", mode="auto")
        assert [t.intent for t in plan.tasks] == ["tutor_question"]

    @pytest.mark.asyncio
    async def test_unknown_intent_does_not_take_over(self):
        cc = _center(True, ["unknown"])
        plan = await cc.route("数据结构好难啊", mode="auto")
        assert [t.intent for t in plan.tasks] == ["tutor_question"]

    @pytest.mark.asyncio
    async def test_auto_domain_intent_does_not_take_over(self):
        # diagnose / profile_building / solve_problem 映射到 auto，不算"明确能力直通"
        cc = _center(True, ["diagnose"])
        plan = await cc.route("数据结构好难啊", mode="auto")
        assert [t.intent for t in plan.tasks] == ["tutor_question"]


class TestTakeoverDoesNotOverrideGate:
    """gate 已命中能力（DIRECT_CAPABILITY）时，接管逻辑不得介入。"""

    @pytest.mark.asyncio
    async def test_direct_capability_not_taken_over_again(self):
        # "帮我出5道题" gate 直接命中 EXERCISE（DIRECT_CAPABILITY），不走语义，
        # 语义 extractor 不应被调用
        ex = _StubExtractor(["resource_gen"])  # 故意给一个矛盾语义结果
        cc = ChatCenter(
            router_agent=RouterAgent(intent_extractor=IntentExtractor(use_mock=True)),
            t4a_enabled=True,
            semantic_extractor=ex,
        )
        plan = await cc.route("帮我出5道进程调度选择题", mode="auto")
        assert ex.calls == 0  # DIRECT_CAPABILITY 不触发语义
        assert "exercise" in [t.mode for t in plan.tasks]
