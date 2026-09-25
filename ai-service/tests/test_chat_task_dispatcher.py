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
        plan = await chat_center.route("hello", mode="auto")
        assert len(plan.tasks) >= 1
        assert plan.tasks[0].mode in ("auto", "inquiry")

    @pytest.mark.asyncio
    async def test_route_auto_multi_intent(self, chat_center):
        plan = await chat_center.route("帮我规划Python学习路径，安排学习计划，再出几道题目")
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

    def test_chat_center_constructs(self):
        center = ChatCenter()
        result = center._get_dispatcher()
        assert result is not None


class TestChatTaskDispatcher:
    @pytest.mark.asyncio
    async def test_inquiry_task_yields_done(self):
        from app.centers.chat_task_dispatcher import ChatTaskDispatcher

        plan = ExecutionPlan(
            tasks=[CenterTask(mode="inquiry", intent="inquiry", input="x", params={"question": "test"})],
            is_clear=False,
        )
        events = []
        async for event in ChatTaskDispatcher().execute(plan):
            events.append(event)
        assert any(e.type.value == "inquiry" for e in events)
        assert any(e.type.value == "done" for e in events)

    @pytest.mark.asyncio
    async def test_unknown_center_returns_error(self):
        from app.centers.chat_task_dispatcher import ChatTaskDispatcher

        plan = ExecutionPlan(
            tasks=[CenterTask(mode="invalid", intent="x", input="x")],
        )
        events = []
        async for event in ChatTaskDispatcher().execute(plan):
            events.append(event)
        done = [e for e in events if e.type.value == "done"][0]
        assert any(r["error"] for r in done.data.get("results", []))

    @pytest.mark.asyncio
    async def test_exercise_mode_routes_to_exercise_center(self):
        from app.centers.chat_task_dispatcher import ChatTaskDispatcher

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
        async for event in ChatTaskDispatcher().execute(plan):
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



class TestCapabilityProductResponse:
    """Task 2/3 回归：能力产物 payload 必须带用户可读 response，
    否则统一聊天里用户看到空回答（评审 cap-01/05/06 空回答根因）。"""

    @pytest.fixture
    def dispatcher(self):
        from app.centers.chat_task_dispatcher import ChatTaskDispatcher
        return ChatTaskDispatcher()

    @staticmethod
    async def _content_payloads(dispatcher, mode, payload):
        plan = ExecutionPlan(
            tasks=[CenterTask(mode=mode, intent="x", input="x", params={}, context={})],
        )
        events = []
        async for event in dispatcher.execute(plan):
            events.append(event)
        return [e.data for e in events if e.type.value == "content" and isinstance(e.data, dict)]

    @pytest.mark.asyncio
    async def test_plan_payload_gains_response_summary(self, dispatcher):
        from app.centers.plan_center import PlanCenter
        from app.centers.chat_task_dispatcher import ChatTaskDispatcher
        from app.centers.schemas import CenterResult

        class FakePlanCenter:
            async def execute(self, task):
                return CenterResult(
                    mode="plan", intent="learning_path", event_type="plan",
                    payload={
                        "type": "plan", "title": "Python 7 天入门", "topic": "Python",
                        "total_steps": 3, "estimated_days": 7,
                        "steps": [{"title": "环境搭建"}, {"title": "基础语法"}, {"title": "小项目"}],
                    },
                    agent="ScheduleAgent", sequence=0,
                )

        agent = ChatTaskDispatcher(plan_center=FakePlanCenter())
        payloads = await self._content_payloads(agent, "plan", {})
        assert payloads, "plan 中心必须产出 content 事件"
        response = payloads[0].get("response", "")
        assert response, "plan payload 必须合成非空 response"
        assert "Python 7 天入门" in response
        assert "3" in response

    @pytest.mark.asyncio
    async def test_visualization_payload_gains_response_summary(self, dispatcher):
        from app.centers.chat_task_dispatcher import ChatTaskDispatcher
        from app.centers.schemas import CenterResult

        class FakeVizCenter:
            async def execute(self, task):
                return CenterResult(
                    mode="visualization", intent="visualize", event_type="visualization",
                    payload={
                        "type": "visualization", "topic": "TCP 三次握手",
                        "blocks": [{"type": "visualization", "content": "graph TD"}],
                    },
                    agent="VisualizationCenter", sequence=0,
                )

        agent = ChatTaskDispatcher(visualization_center=FakeVizCenter())
        payloads = await self._content_payloads(agent, "visualization", {})
        assert payloads, "visualization 中心必须产出 content 事件"
        response = payloads[0].get("response", "")
        assert response, "visualization payload 必须合成非空 response"
        assert "TCP 三次握手" in response

    @pytest.mark.asyncio
    async def test_existing_response_not_rewritten(self, dispatcher):
        from app.centers.chat_task_dispatcher import ChatTaskDispatcher
        from app.centers.schemas import CenterResult

        class FakeResourceCenter:
            async def execute(self, task):
                return CenterResult(
                    mode="resource", intent="resource_gen", event_type="content",
                    payload={"response": "已为您生成学习文档，共 7 个内容块。"},
                    agent="ResourceGenWorkflow", sequence=0,
                )

        agent = ChatTaskDispatcher(resource_center=FakeResourceCenter())
        payloads = await self._content_payloads(agent, "resource", {})
        assert payloads[0]["response"] == "已为您生成学习文档，共 7 个内容块。"
