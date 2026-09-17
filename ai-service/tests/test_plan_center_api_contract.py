"""PlanCenter API 契约离线测试。

不调真实 LLM、真实 GraphService、真实网络。仅验证：
- create_from_path() 成功路径产出完整 API payload
- execute() 与 create_from_path() 共享同一份 _build_plan_payload
- 依赖注入生效：注入实例则使用，未注入则走 fallback（用 is not None 不用 or）
- 空 steps 抛 PlanGenerationError
- _normalize_milestones / _enrich_steps_with_nodes 行为对齐 API 旧实现
- API 路由 /internal/plans/create-from-path 的 HTTP 契约：200/400/500 三种分支
- API 路由只委派给 PlanCenter，不再重复 Goal → Decompose → Schedule（结构性搜索）
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


def _make_graph_service_with_unrelated_nodes():
    """返回节点 topic 与测试步骤不相关的 graph_service，确保所有 steps 进入 unknowns。"""
    from unittest.mock import MagicMock

    graph = MagicMock()
    graph.load_skeleton.return_value = {
        "nodes": [
            {"id": "other1", "name": "其他主题1", "category": "基础", "description": ""},
            {"id": "other2", "name": "其他主题2", "category": "基础", "description": ""},
        ]
    }
    graph._all_nodes.return_value = [
        {"id": "other1", "name": "其他主题1", "category": "基础"},
        {"id": "other2", "name": "其他主题2", "category": "基础"},
    ]
    return graph


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


class TestGenerateBasePlanOrchestration:
    """P1.1 锁定：execute() 与 create_from_path() 都复用 _generate_base_plan()。"""

    @pytest.mark.asyncio
    async def test_execute_calls_generate_base_plan_once(self):
        """execute() 路径：独立 Center，patch _generate_base_plan，断言 await 一次。"""
        from unittest.mock import AsyncMock, patch
        from app.centers.plan_center import PlanCenter
        from app.centers.schemas import CenterTask

        fake_payload = {
            "type": "plan",
            "title": "X学习计划",
            "topic": "X",
            "total_steps": 1,
            "steps": [{"topic": "t", "estimated_days": 1, "topic_difficulty": 3, "status": "pending"}],
            "milestones": [],
            "estimated_days": 7,
            "daily_capacity": 3,
            "goal": {},
            "concept_graph": {},
            "summary": "OK",
        }

        center = PlanCenter(
            goal_agent=AsyncMock(),
            decompose_agent=AsyncMock(),
            schedule_agent=AsyncMock(),
        )

        with patch.object(center, "_generate_base_plan", AsyncMock(return_value=fake_payload)) as mock_method:
            task = CenterTask(
                mode="plan",
                intent="learning_path",
                input="我想学 X",
                params={"topic": "X"},
                context={"student_profile": {}},
            )
            result = await center.execute(task)

        mock_method.assert_awaited_once()
        # execute() 包装 CenterResult；payload 应等于 _generate_base_plan 的返回值
        assert result.event_type == "plan"
        assert result.payload["title"] == "X学习计划"
        assert result.payload["total_steps"] == 1

    @pytest.mark.asyncio
    async def test_create_from_path_calls_generate_base_plan_once(self):
        """create_from_path() 路径：独立 Center，patch _generate_base_plan，断言 await 一次。"""
        from unittest.mock import AsyncMock, patch
        from app.centers.plan_center import PlanCenter

        fake_payload = {
            "type": "plan",
            "title": "Transformer学习计划",
            "topic": "Transformer",
            "total_steps": 2,
            "steps": [
                {"topic": "注意力机制", "estimated_days": 1, "topic_difficulty": 3, "status": "pending"},
                {"topic": "编码器", "estimated_days": 1, "topic_difficulty": 3, "status": "pending"},
            ],
            "milestones": [],
            "estimated_days": 7,
            "daily_capacity": 3,
            "goal": {},
            "concept_graph": {},
            "summary": "OK",
        }

        center = PlanCenter(
            goal_agent=AsyncMock(),
            decompose_agent=AsyncMock(),
            schedule_agent=AsyncMock(),
            graph_service=_make_fake_graph_service(),
            step_classifier=_make_fake_step_classifier(),
        )

        with patch.object(center, "_generate_base_plan", AsyncMock(return_value=fake_payload)) as mock_method:
            result = await center.create_from_path(
                topic="Transformer",
                course_id="ai_intro",
                student_profile={},
            )

        mock_method.assert_awaited_once()
        # create_from_path 包装 API payload；course_id 应回填、total_steps 应等于 steps 数
        assert result["course_id"] == "ai_intro"
        assert result["total_steps"] == 2
        assert result["title"] == "Transformer学习计划"


class TestEnrichStepsConservativeFallback:
    """P1.1 锁定：_enrich_steps_with_nodes 失败时只丢 knowledge_node_id，不丢原始 steps。"""

    _UNMATCHED_STEPS = [
        {"topic": "注意力机制", "estimated_days": 1, "topic_difficulty": 3, "status": "pending"},
        {"topic": "编码器", "estimated_days": 1, "topic_difficulty": 3, "status": "pending"},
    ]

    @pytest.mark.asyncio
    async def test_graph_service_failure_preserves_all_steps(self):
        """graph_service.load_skeleton() 抛异常：所有原始步骤必须按顺序返回，knowledge_node_id=""。"""
        from unittest.mock import AsyncMock, MagicMock
        from app.centers.plan_center import PlanCenter

        graph = MagicMock()
        graph.load_skeleton.side_effect = RuntimeError("graph unavailable")
        graph._all_nodes.return_value = []

        classifier_called = {"flag": False}

        async def classifier(exercises, knowledge_nodes, course_id):
            classifier_called["flag"] = True
            return []

        center = PlanCenter(
            goal_agent=AsyncMock(),
            decompose_agent=AsyncMock(),
            schedule_agent=AsyncMock(),
            graph_service=graph,
            step_classifier=classifier,
        )

        result = await center._enrich_steps_with_nodes(self._UNMATCHED_STEPS, "ai_intro")

        assert len(result) == 2
        assert [step["topic"] for step in result] == ["注意力机制", "编码器"]
        assert all(step["knowledge_node_id"] == "" for step in result)
        assert all("suggested_resource_types" in step for step in result)
        # 图谱失败，分类器也不应被调用
        assert classifier_called["flag"] is False

    @pytest.mark.asyncio
    async def test_empty_skeleton_preserves_all_steps_without_calling_classifier(self):
        """load_skeleton 返回 {"nodes": []}, _all_nodes 返回 []：所有步骤必须返回，分类器不能被调。"""
        from unittest.mock import AsyncMock, MagicMock
        from app.centers.plan_center import PlanCenter

        graph = MagicMock()
        graph.load_skeleton.return_value = {"nodes": []}
        graph._all_nodes.return_value = []

        classifier_called = {"flag": False}

        async def classifier(exercises, knowledge_nodes, course_id):
            classifier_called["flag"] = True
            return []

        center = PlanCenter(
            goal_agent=AsyncMock(),
            decompose_agent=AsyncMock(),
            schedule_agent=AsyncMock(),
            graph_service=graph,
            step_classifier=classifier,
        )

        result = await center._enrich_steps_with_nodes(self._UNMATCHED_STEPS, "ai_intro")

        assert len(result) == 2
        assert [step["step_order"] for step in result] == [1, 2]
        assert all(step["knowledge_node_id"] == "" for step in result)
        # 静态节点为空，没必要调用分类器
        assert classifier_called["flag"] is False

    @pytest.mark.asyncio
    async def test_classifier_failure_preserves_all_steps_with_empty_node_id(self):
        """分类器抛异常：所有原始步骤按 step_order 排序后返回，knowledge_node_id=""。"""
        from unittest.mock import AsyncMock
        from app.centers.plan_center import PlanCenter

        graph = _make_graph_service_with_unrelated_nodes()

        async def classifier(exercises, knowledge_nodes, course_id):
            raise RuntimeError("classifier unavailable")

        center = PlanCenter(
            goal_agent=AsyncMock(),
            decompose_agent=AsyncMock(),
            schedule_agent=AsyncMock(),
            graph_service=graph,
            step_classifier=classifier,
        )

        result = await center._enrich_steps_with_nodes(self._UNMATCHED_STEPS, "ai_intro")

        assert len(result) == 2
        assert [step["step_order"] for step in result] == [1, 2]
        assert [step["topic"] for step in result] == ["注意力机制", "编码器"]
        assert all(step["knowledge_node_id"] == "" for step in result)

    @pytest.mark.asyncio
    async def test_multiple_unknown_steps_get_correct_node_id_mapping(self):
        """分类器返回 [index:0→node-a, index:1→node-b]：两个未知步骤必须各自落到正确的 node_id。

        实现不能从 exercise 字典读取不存在的 index 构造映射——只能从 classifier 返回的 results 中取 index。
        """
        from unittest.mock import AsyncMock
        from app.centers.plan_center import PlanCenter

        graph = _make_graph_service_with_unrelated_nodes()

        async def classifier(exercises, knowledge_nodes, course_id):
            return [
                {"index": 0, "knowledge_node_id": "node-a"},
                {"index": 1, "knowledge_node_id": "node-b"},
            ]

        center = PlanCenter(
            goal_agent=AsyncMock(),
            decompose_agent=AsyncMock(),
            schedule_agent=AsyncMock(),
            graph_service=graph,
            step_classifier=classifier,
        )

        result = await center._enrich_steps_with_nodes(self._UNMATCHED_STEPS, "ai_intro")

        assert len(result) == 2
        assert result[0]["step_order"] == 1
        assert result[0]["topic"] == "注意力机制"
        assert result[0]["knowledge_node_id"] == "node-a"
        assert result[1]["step_order"] == 2
        assert result[1]["topic"] == "编码器"
        assert result[1]["knowledge_node_id"] == "node-b"


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


class TestCreatePlanFromPathHttpContract:
    """API 层 HTTP 契约：/internal/plans/create-from-path 的 200/400/500 分支。"""

    @pytest.fixture
    def fake_center_factory(self):
        """patch internal_api._get_plan_center，返回一个可控制行为的假 Center。"""
        from unittest.mock import AsyncMock, patch

        def _make(return_value=None, side_effect=None):
            fake_center = AsyncMock()
            if side_effect is not None:
                fake_center.create_from_path.side_effect = side_effect
            else:
                fake_center.create_from_path.return_value = return_value
            return patch("internal_api._get_plan_center", return_value=fake_center), fake_center

        return _make

    @pytest.mark.asyncio
    async def test_success_returns_200_with_payload(self, fake_center_factory):
        """假 Center 返回完整 dict → HTTP 200，body.success is True，data 与假 Center 一致。"""
        from app.api.errors import api_success
        from internal_api import CreatePlanFromPathRequest

        payload = {
            "course_id": "ai_intro",
            "total_steps": 2,
            "steps": [
                {"step_order": 1, "topic": "注意力机制", "knowledge_node_id": "attention",
                 "status": "pending", "estimated_days": 1, "topic_difficulty": 3,
                 "suggested_resource_types": ["document", "mindmap", "exercise"]},
            ],
            "title": "Transformer学习计划",
            "milestones": [{"milestone_id": "m1", "after_step": 1, "description": "完成基础"}],
            "estimated_days": 7,
            "daily_capacity": 3,
            "concept_graph": {"macro_topics": []},
            "summary": "OK",
        }
        ctx, fake_center = fake_center_factory(return_value=payload)
        with ctx:
            from fastapi.testclient import TestClient
            from internal_api import router
            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)

            response = client.post("/internal/plans/create-from-path", json={
                "user_id": 123,
                "course_id": "ai_intro",
                "topic": "学习 Transformer",
                "student_profile": {"level": "beginner"},
            })

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] == payload

        # Center 只调一次，参数对齐
        fake_center.create_from_path.assert_awaited_once()
        call_kwargs = fake_center.create_from_path.await_args.kwargs
        assert call_kwargs["topic"] == "学习 Transformer"
        assert call_kwargs["course_id"] == "ai_intro"
        assert call_kwargs["student_profile"] == {"level": "beginner"}

    @pytest.mark.asyncio
    async def test_plan_generation_error_returns_400(self, fake_center_factory):
        """假 Center 抛 PlanGenerationError → HTTP 400 + errorCode=GENERATION_FAILED。"""
        from app.centers.plan_center import PlanGenerationError

        ctx, _ = fake_center_factory(side_effect=PlanGenerationError("未能生成学习计划，请确认输入更具体"))
        with ctx:
            from fastapi.testclient import TestClient
            from internal_api import router
            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)

            response = client.post("/internal/plans/create-from-path", json={
                "user_id": 123,
                "course_id": "ai_intro",
                "topic": "模糊主题",
                "student_profile": {},
            })

        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False
        assert body["errorCode"] == "GENERATION_FAILED"
        assert "未能生成学习计划" in body["error"]

    @pytest.mark.asyncio
    async def test_unexpected_error_returns_500(self, fake_center_factory):
        """假 Center 抛 RuntimeError → HTTP 500 + errorCode=INTERNAL_ERROR。"""
        ctx, _ = fake_center_factory(side_effect=RuntimeError("boom"))
        with ctx:
            from fastapi.testclient import TestClient
            from internal_api import router
            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)

            response = client.post("/internal/plans/create-from-path", json={
                "user_id": 123,
                "course_id": "ai_intro",
                "topic": "学习 X",
                "student_profile": {},
            })

        assert response.status_code == 500
        body = response.json()
        assert body["success"] is False
        assert body["errorCode"] == "INTERNAL_ERROR"


class TestApiNoLongerReimplementsPipeline:
    """结构性断言：API 路由内不再直接调 Goal/Decompose/Schedule Agent，不再有 enrichment/normalize。"""

    def test_create_plan_from_path_route_does_not_call_agents_directly(self):
        """读取路由函数源码，确认不出现 Agent 构造与三段式调用。"""
        import inspect
        from internal_api import create_plan_from_path

        source = inspect.getsource(create_plan_from_path)
        # 路由函数体内不能直接构造 Agent
        assert "GoalAgent(" not in source, "create_plan_from_path 仍直接构造 GoalAgent"
        assert "DecomposeAgent(" not in source, "create_plan_from_path 仍直接构造 DecomposeAgent"
        assert "ScheduleAgent(" not in source, "create_plan_from_path 仍直接构造 ScheduleAgent"
        assert "goal_agent.run" not in source, "create_plan_from_path 仍直接调 goal_agent.run"
        assert "decompose_agent.run" not in source, "create_plan_from_path 仍直接调 decompose_agent.run"
        assert "schedule_agent.run" not in source, "create_plan_from_path 仍直接调 schedule_agent.run"
        # 必须委派给 _get_plan_center().create_from_path
        assert "_get_plan_center" in source
        assert "create_from_path" in source

    def test_internal_api_no_longer_has_enrich_or_normalize_helpers(self):
        """API 模块不再持有旧的领域辅助函数。"""
        import internal_api

        assert not hasattr(internal_api, "_enrich_steps_with_nodes"), "API 仍持有 _enrich_steps_with_nodes"
        assert not hasattr(internal_api, "_normalize_milestones"), "API 仍持有 _normalize_milestones"
        # 但 _compute_next_milestone 必须保留（计划状态端点还在用）
        assert hasattr(internal_api, "_compute_next_milestone"), "_compute_next_milestone 被误删"
