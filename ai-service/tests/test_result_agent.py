import asyncio

import pytest

from app.centers.chat_center import ChatCenter
from app.centers.router_agent import RouterAgent
from app.centers.schemas import CenterTask, ExecutionPlan
from app.services.intent_extractor import IntentExtractor


class TestChatCenter:
    @pytest.fixture
    def chat_center(self):
        return ChatCenter(
            router_agent=RouterAgent(intent_extractor=IntentExtractor(use_mock=True)),
        )

    @pytest.mark.asyncio
    async def test_route_manual_mode(self, chat_center):
        plan = await chat_center.route("hello", mode="tutor")
        assert len(plan.tasks) == 1
        assert plan.tasks[0].mode == "auto"

    @pytest.mark.asyncio
    async def test_route_auto_multi_intent(self, chat_center):
        plan = await chat_center.route("规划Python路径并出3道题")
        assert len(plan.tasks) >= 2

    @pytest.mark.asyncio
    async def test_execute_inquiry_event(self, chat_center):
        plan = ExecutionPlan(
            tasks=[CenterTask(mode="inquiry", intent="inquiry", input="x", params={"question": "test"})],
            is_clear=False,
        )
        events = []
        async for event in chat_center.execute(plan):
            events.append(event)
        assert any(e.type.value == "inquiry" for e in events)
        assert any(e.type.value == "done" for e in events)

    def test_p2_agents_created_when_pipeline_enabled(self):
        center = ChatCenter(use_p1_agents=True)
        center._get_result()
        assert center._reflection_agent is not None
        assert center._project_agent is not None
        assert center._exercise_variant_agent is not None

    def test_p2_agents_not_created_when_pipeline_disabled(self):
        center = ChatCenter(use_p1_agents=False)
        center._get_result()
        assert not hasattr(center, "_reflection_agent")


class TestResultAgent:
    @pytest.mark.asyncio
    async def test_inquiry_task_yields_done(self):
        from app.centers.result_agent import ResultAgent

        plan = ExecutionPlan(
            tasks=[CenterTask(mode="inquiry", intent="inquiry", input="x", params={"question": "test"})],
            is_clear=False,
        )
        events = []
        async for event in ResultAgent().execute(plan):
            events.append(event)
        assert any(e.type.value == "inquiry" for e in events)
        assert any(e.type.value == "done" for e in events)

    @pytest.mark.asyncio
    async def test_unknown_center_returns_error(self):
        from app.centers.result_agent import ResultAgent

        plan = ExecutionPlan(
            tasks=[CenterTask(mode="invalid", intent="x", input="x")],
        )
        events = []
        async for event in ResultAgent().execute(plan):
            events.append(event)
        done = [e for e in events if e.type.value == "done"][0]
        assert any(r["error"] for r in done.data.get("results", []))

    @pytest.mark.asyncio
    async def test_exercise_mode_routes_to_exercise_center(self):
        from app.centers.result_agent import ResultAgent

        plan = ExecutionPlan(
            tasks=[CenterTask(
                mode="exercise",
                intent="exercise_gen",
                input="出3道机器学习练习题",
                params={"topic": "机器学习", "count": 3, "difficulty": "medium"},
                context={"student_profile": {}},
            )],
        )
        events = []
        async for event in ResultAgent().execute(plan):
            events.append(event)
        done = [e for e in events if e.type.value == "done"][0]
        result = done.data["results"][0]
        assert result["mode"] == "exercise"
        assert result["agent"] == "ExerciseAgent"


class TestAutoCenterRouting:
    @pytest.mark.asyncio
    async def test_profile_building_routes_to_profile_agent(self):
        from app.centers.auto_center import AutoCenter
        from app.centers.schemas import CenterTask

        center = AutoCenter()
        task = CenterTask(
            mode="auto",
            intent="profile_building",
            input="我是新手，想学Python",
            params={"message": "我是新手，想学Python"},
            context={"student_profile": {}, "messages": [{"role": "user", "content": "我是新手，想学Python"}]},
        )
        result = await center.execute(task)
        assert result.agent == "ProfileAgent"
        assert "current_profile" in result.payload

