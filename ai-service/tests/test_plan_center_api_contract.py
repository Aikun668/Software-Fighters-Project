"""PlanCenter API 契约离线测试（Task 2 阶段：覆盖 create_from_path + 共享 payload + 依赖注入）。

不调真实 LLM、真实 GraphService、真实网络。仅验证：
- create_from_path() 成功路径产出完整 API payload
- execute() 与 create_from_path() 共享同一份 _build_plan_payload
- 依赖注入生效：注入实例则使用，未注入则走 fallback（用 is not None 不用 or）
- 空 steps 抛 PlanGenerationError
- _normalize_milestones / _enrich_steps_with_nodes 行为对齐 API 旧实现

API 层去重 / _get_plan_center 单例 / internal_api 旧实现删除 → Task 3。
"""

import pytest


def _build_goal_state(target_topic: str = "Transformer") -> dict:
    return {
        "goal_title": f"学会{target_topic}",
        "target_topic": target_topic,
        "target_level": "understand",
        "deadline": "",
        "motivation": "",
        "constraints": [],
    }


def _build_decompose_state() -> dict:
    return {
        "macro_topics": [{"name": "注意力机制"}, {"name": "编码器-解码器"}],
        "micro_skills": [],
        "prerequisites": [],
    }


def _build_schedule_state(topic: str = "Transformer") -> dict:
    return {
        "plan_title": f"{topic}学习计划",
        "steps": [
            {"topic": "注意力机制", "estimated_days": 1, "topic_difficulty": 3, "status": "pending"},
            {"topic": "编码器", "estimated_days": 1, "topic_difficulty": 3, "status": "pending"},
        ],
        "milestones": ["完成基础", "进入编码器-解码器结构"],
        "estimated_days": 7,
        "daily_capacity": 3,
        "response": "OK",
    }


def _make_fake_graph_service():
    """假 GraphService：返回固定 dynamic_nodes + skeleton。

    用 MagicMock 实现，方便用 call_count 断言调用情况。
    """
    from unittest.mock import MagicMock

    graph_service = MagicMock()
    graph_service.load_skeleton.return_value = {
        "nodes": [
            {"id": "attention", "name": "注意力机制", "category": "基础", "description": ""},
            {"id": "encoder", "name": "编码器", "category": "基础", "description": ""},
        ]
    }
    graph_service._all_nodes.return_value = [
        {"id": "attention", "name": "注意力机制", "category": "基础"},
        {"id": "encoder", "name": "编码器", "category": "基础"},
    ]
    return graph_service


def _make_fake_step_classifier():
    """假 step_classifier：未匹配步骤全部映射到 attention。"""
    async def fake(exercises, knowledge_nodes, course_id):
        return [{"index": e.get("index", 0), "knowledge_node_id": "attention"} for e in exercises]
    return fake


class TestPlanCenterCreateFromPath:
    @pytest.mark.asyncio
    async def test_create_from_path_returns_full_api_payload(self):
        """注入假 Agent + 假 graph_service + 假 step_classifier，验证 create_from_path 返回完整 API payload。"""
        from unittest.mock import AsyncMock
        from app.centers.plan_center import PlanCenter

        goal_agent = AsyncMock()
        goal_agent.run = AsyncMock(return_value=_build_goal_state())
        decompose_agent = AsyncMock()
        decompose_agent.run = AsyncMock(return_value=_build_decompose_state())
        schedule_agent = AsyncMock()
        schedule_agent.run = AsyncMock(return_value=_build_schedule_state())

        center = PlanCenter(
            goal_agent=goal_agent,
            decompose_agent=decompose_agent,
            schedule_agent=schedule_agent,
            graph_service=_make_fake_graph_service(),
            step_classifier=_make_fake_step_classifier(),
        )

        result = await center.create_from_path(
            topic="学习 Transformer",
            course_id="ai_intro",
            student_profile={},
        )

        assert result["course_id"] == "ai_intro"
        assert result["total_steps"] == 2
        assert result["title"] == "Transformer学习计划"
        assert result["estimated_days"] == 7
        assert result["daily_capacity"] == 3
        assert result["summary"] == "OK"

        # steps 包含 knowledge_node_id 和 suggested_resource_types
        step1, step2 = result["steps"]
        assert step1["step_order"] == 1
        assert step1["topic"] == "注意力机制"
        assert step1["knowledge_node_id"] == "attention"
        assert step1["status"] == "pending"
        assert step1["estimated_days"] == 1
        assert step1["topic_difficulty"] == 3
        assert "document" in step1["suggested_resource_types"]
        assert step2["step_order"] == 2
        assert step2["knowledge_node_id"] == "encoder"
        assert "suggested_resource_types" in step2

        # milestones 被标准化：round(2 * (i+1) / (n+1))
        # i=0: round(2/3) = 1; i=1: round(4/3) = 1
        assert result["milestones"] == [
            {"milestone_id": "m1", "after_step": 1, "description": "完成基础"},
            {"milestone_id": "m2", "after_step": 1, "description": "进入编码器-解码器结构"},
        ]

        # concept_graph 是 decomposition 的子集
        assert "macro_topics" in result["concept_graph"]
        assert result["concept_graph"]["macro_topics"] == _build_decompose_state()["macro_topics"]

        # 三段 Agent 各调一次
        goal_agent.run.assert_awaited_once()
        decompose_agent.run.assert_awaited_once()
        schedule_agent.run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_from_path_raises_on_empty_steps(self):
        """Schedule 返回空 steps → 抛 PlanGenerationError，由 API 层映射为 400。"""
        from unittest.mock import AsyncMock
        from app.centers.plan_center import PlanCenter, PlanGenerationError

        empty_schedule_state = {
            "plan_title": "空计划",
            "steps": [],
            "milestones": [],
            "estimated_days": 7,
            "daily_capacity": 3,
            "response": "",
        }

        center = PlanCenter(
            goal_agent=AsyncMock(),
            decompose_agent=AsyncMock(),
            schedule_agent=AsyncMock(),
            graph_service=_make_fake_graph_service(),
            step_classifier=_make_fake_step_classifier(),
        )
        center.goal_agent.run = AsyncMock(return_value=_build_goal_state())
        center.decompose_agent.run = AsyncMock(return_value=_build_decompose_state())
        center.schedule_agent.run = AsyncMock(return_value=empty_schedule_state)

        with pytest.raises(PlanGenerationError) as exc:
            await center.create_from_path(
                topic="模糊主题",
                course_id="ai_intro",
                student_profile={},
            )
        assert "未能生成学习计划" in str(exc.value)

    @pytest.mark.asyncio
    async def test_dependency_injection_uses_provided_instances(self):
        """注入 graph_service 后，绝不调用 fallback（不导入 get_graph_service）。"""
        from unittest.mock import AsyncMock, MagicMock
        from app.centers.plan_center import PlanCenter

        graph_service = MagicMock()
        graph_service.load_skeleton.return_value = {"nodes": []}
        graph_service._all_nodes.return_value = []

        classifier_called = {"flag": False}

        async def classifier(exercises, knowledge_nodes, course_id):
            classifier_called["flag"] = True
            return []

        center = PlanCenter(
            goal_agent=AsyncMock(),
            decompose_agent=AsyncMock(),
            schedule_agent=AsyncMock(),
            graph_service=graph_service,
            step_classifier=classifier,
        )
        center.goal_agent.run = AsyncMock(return_value=_build_goal_state())
        center.decompose_agent.run = AsyncMock(return_value=_build_decompose_state())
        center.schedule_agent.run = AsyncMock(return_value=_build_schedule_state())

        await center.create_from_path(
            topic="学习 Transformer",
            course_id="ai_intro",
            student_profile={},
        )

        # 注入的 graph_service.load_skeleton 被调用
        graph_service.load_skeleton.assert_called_once()
        graph_service._all_nodes.assert_called_once_with("ai_intro")

    @pytest.mark.asyncio
    async def test_dependency_injection_none_uses_fallback(self):
        """graph_service=None 时走现网 fallback（不抛异常，能完成调用）。"""
        from unittest.mock import AsyncMock
        from app.centers.plan_center import PlanCenter

        center = PlanCenter(
            goal_agent=AsyncMock(),
            decompose_agent=AsyncMock(),
            schedule_agent=AsyncMock(),
            graph_service=None,
            step_classifier=None,
        )
        center.goal_agent.run = AsyncMock(return_value=_build_goal_state())
        center.decompose_agent.run = AsyncMock(return_value=_build_decompose_state())
        center.schedule_agent.run = AsyncMock(return_value=_build_schedule_state())

        # 不抛异常即视为走了 fallback；不强校验 graph 内部结果（避免依赖真实骨架）
        result = await center.create_from_path(
            topic="学习 Transformer",
            course_id="ai_intro",
            student_profile={},
        )
        assert "steps" in result
        assert "milestones" in result


class TestPlanCenterSharedPayload:
    @pytest.mark.asyncio
    async def test_execute_and_create_from_path_share_three_segment_results(self):
        """execute() 和 create_from_path() 跑同样的三段 Agent，共享 _build_plan_payload。"""
        from unittest.mock import AsyncMock
        from app.centers.plan_center import PlanCenter
        from app.centers.schemas import CenterTask

        goal_agent = AsyncMock()
        goal_agent.run = AsyncMock(return_value=_build_goal_state())
        decompose_agent = AsyncMock()
        decompose_agent.run = AsyncMock(return_value=_build_decompose_state())
        schedule_agent = AsyncMock()
        schedule_agent.run = AsyncMock(return_value=_build_schedule_state())

        graph_service = _make_fake_graph_service()
        step_classifier = _make_fake_step_classifier()

        center = PlanCenter(
            goal_agent=goal_agent,
            decompose_agent=decompose_agent,
            schedule_agent=schedule_agent,
            graph_service=graph_service,
            step_classifier=step_classifier,
        )

        task = CenterTask(
            mode="plan",
            intent="learning_path",
            input="我想学 Transformer",
            params={"topic": "Transformer"},
            context={"student_profile": {}},
        )

        # execute() 路径：不动 graph/classifier（聊天侧行为不变）
        result = await center.execute(task)
        assert result.event_type == "plan"
        assert "goal" in result.payload
        assert result.payload["total_steps"] == 2
        assert result.payload["steps"][0]["topic"] == "注意力机制"
        # execute() 不应触发图谱增强（保持聊天侧行为不变）
        assert graph_service.load_skeleton.call_count == 0
        assert graph_service._all_nodes.call_count == 0

        # 重置 mock 后跑 create_from_path() 路径
        goal_agent.reset_mock()
        decompose_agent.reset_mock()
        schedule_agent.reset_mock()
        graph_service.load_skeleton.reset_mock()
        graph_service._all_nodes.reset_mock()

        api_result = await center.create_from_path(
            topic="Transformer",
            course_id="ai_intro",
            student_profile={},
        )

        # 两路径 Agent 都被调用
        goal_agent.run.assert_awaited_once()
        decompose_agent.run.assert_awaited_once()
        schedule_agent.run.assert_awaited_once()

        # create_from_path 触发了图谱增强
        graph_service.load_skeleton.assert_called_once()
        graph_service._all_nodes.assert_called_once_with("ai_intro")

        # 两个路径的 steps 主题一致（共享 _build_plan_payload）
        execute_steps_topics = [s["topic"] for s in result.payload["steps"]]
        create_steps_topics = [s["topic"] for s in api_result["steps"]]
        assert execute_steps_topics == create_steps_topics == ["注意力机制", "编码器"]

        # create_from_path 多出 enrichment 字段（knowledge_node_id）
        for s in api_result["steps"]:
            assert "knowledge_node_id" in s
            assert "suggested_resource_types" in s

        # execute 路径无 enrichment 字段（保持聊天侧不变）
        for s in result.payload["steps"]:
            assert "knowledge_node_id" not in s


class TestNormalizeMilestones:
    def test_string_list_normalized(self):
        from app.centers.plan_center import PlanCenter

        # round() 用 banker's rounding：round(1.5)=2, round(3.0)=3, round(4.5)=4
        result = PlanCenter._normalize_milestones(["基础", "进阶", "实战"], total_steps=6)
        assert result == [
            {"milestone_id": "m1", "after_step": 2, "description": "基础"},
            {"milestone_id": "m2", "after_step": 3, "description": "进阶"},
            {"milestone_id": "m3", "after_step": 4, "description": "实战"},
        ]

    def test_dict_list_passed_through(self):
        from app.centers.plan_center import PlanCenter

        already = [
            {"milestone_id": "x1", "after_step": 1, "description": "已规范"},
        ]
        assert PlanCenter._normalize_milestones(already, total_steps=5) == already

    def test_empty_list_returns_empty(self):
        from app.centers.plan_center import PlanCenter

        assert PlanCenter._normalize_milestones([], total_steps=3) == []
