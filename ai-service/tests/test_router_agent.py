import pytest

from app.centers.router_agent import RouterAgent
from app.centers.schemas import ExecutionPlan
from app.services.intent_extractor import IntentExtractor


class TestRouterAgent:
    @pytest.fixture
    def router(self):
        return RouterAgent(intent_extractor=IntentExtractor(use_mock=True))

    @pytest.mark.asyncio
    async def test_manual_mode_bypasses_intent(self, router):
        plan = await router.route("hello", mode="tutor")
        assert isinstance(plan, ExecutionPlan)
        assert len(plan.tasks) == 1
        assert plan.tasks[0].mode == "auto"
        assert plan.tasks[0].intent == "tutor_question"

    @pytest.mark.asyncio
    async def test_auto_mode_multi_intent_sorted(self, router):
        plan = await router.route("帮我规划Python学习路径，安排学习计划，再出几道题目")
        assert len(plan.tasks) >= 2
        modes = [t.mode for t in plan.tasks]
        assert modes.index("plan") < modes.index("exercise")

    @pytest.mark.asyncio
    async def test_empty_message_returns_inquiry(self, router):
        plan = await router.route("   ")
        assert not plan.is_clear
        assert plan.tasks[0].mode == "inquiry"

    @pytest.mark.asyncio
    async def test_vague_message_may_be_tutor(self, router):
        plan = await router.route("随便聊聊")
        assert plan.tasks[0].intent == "tutor_question"
        assert plan.is_clear is True

    @pytest.mark.asyncio
    async def test_max_intents_respected(self, router):
        plan = await router.route("规划路径出题生成资源画知识图谱", max_intents=2)
        assert len(plan.tasks) <= 2
