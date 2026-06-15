import pytest


class TestDecomposeAgent:
    @pytest.mark.asyncio
    async def test_fallback_without_llm(self):
        from app.agents.decompose_agent import DecomposeAgent

        agent = DecomposeAgent(use_mock_llm=True)
        state = await agent.run({"topic": "机器学习", "context": "", "student_profile": {}})

        assert "macro_topics" in state
        assert "micro_skills" in state
        assert len(state["macro_topics"]) > 0
        assert state["response"]

    @pytest.mark.asyncio
    async def test_skeleton_fallback_for_unknown_topic(self):
        from app.agents.decompose_agent import DecomposeAgent

        agent = DecomposeAgent(use_mock_llm=True)
        state = await agent.run({"topic": "完全不存在的主题XYZ", "context": "", "student_profile": {}})

        assert isinstance(state.get("macro_topics"), list)
        assert isinstance(state.get("prerequisites"), list)

    @pytest.mark.asyncio
    async def test_empty_topic_produces_fallback(self):
        from app.agents.decompose_agent import DecomposeAgent

        agent = DecomposeAgent(use_mock_llm=True)
        state = await agent.run({"topic": "", "context": "", "student_profile": {}})

        assert isinstance(state.get("macro_topics"), list)
        assert "response" in state


class TestLayeredExplainAgent:
    @pytest.mark.asyncio
    async def test_fallback_generates_three_layers(self):
        from app.agents.layered_explain_agent import LayeredExplainAgent

        agent = LayeredExplainAgent(use_mock_llm=True)
        state = await agent.run({"topic": "梯度下降", "student_profile": {}, "code_language": "python"})

        assert "intuition_layer" in state
        assert "formal_layer" in state
        assert "code_layer" in state
        assert state["code_layer"].get("code")

    @pytest.mark.asyncio
    async def test_missing_code_language_defaults_to_python(self):
        from app.agents.layered_explain_agent import LayeredExplainAgent

        agent = LayeredExplainAgent(use_mock_llm=True)
        state = await agent.run({"topic": "反向传播", "student_profile": {}})
        assert state["code_layer"].get("language") == "python"


class TestDiagnoseAgent:
    @pytest.mark.asyncio
    async def test_bkt_update_increases_on_correct(self):
        from app.agents.diagnose_agent import DiagnoseAgent

        agent = DiagnoseAgent()
        state = await agent.run({
            "topic": "神经网络",
            "skills": ["神经网络"],
            "prior_mastery": {"神经网络": 0.3},
            "attempts": [
                {"skill": "神经网络", "question": {"question_type": "choice", "correct_answer": "A"}, "user_answer": "A"},
            ],
        })

        mastery = state["mastery_vector"]["神经网络"]
        assert mastery > 0.3
        assert 0 <= mastery <= 1

    @pytest.mark.asyncio
    async def test_bkt_update_decreases_on_wrong(self):
        from app.agents.diagnose_agent import DiagnoseAgent

        agent = DiagnoseAgent()
        state = await agent.run({
            "topic": "神经网络",
            "skills": ["神经网络"],
            "prior_mastery": {"神经网络": 0.8},
            "attempts": [
                {"skill": "神经网络", "question": {"question_type": "choice", "correct_answer": "A"}, "user_answer": "B"},
            ],
        })

        mastery = state["mastery_vector"]["神经网络"]
        assert mastery < 0.8

    @pytest.mark.asyncio
    async def test_report_identifies_next_skill(self):
        from app.agents.diagnose_agent import DiagnoseAgent

        agent = DiagnoseAgent()
        state = await agent.run({
            "topic": "综合诊断",
            "skills": ["A", "B"],
            "prior_mastery": {"A": 0.9, "B": 0.2},
            "attempts": [],
        })

        assert state["next_skill"] == "B"
        assert "B" in state["report"]["weaknesses"]

    @pytest.mark.asyncio
    async def test_empty_skills_does_not_crash(self):
        from app.agents.diagnose_agent import DiagnoseAgent

        agent = DiagnoseAgent()
        state = await agent.run({
            "topic": "诊断",
            "skills": [],
            "prior_mastery": {},
            "attempts": [],
        })

        assert isinstance(state["mastery_vector"], dict)
        assert state["report"]["confidence"] >= 0

    @pytest.mark.asyncio
    async def test_bkt_boundary_full_mastery(self):
        from app.agents.diagnose_agent import DiagnoseAgent

        agent = DiagnoseAgent()
        state = await agent.run({
            "topic": "边界测试",
            "skills": ["X"],
            "prior_mastery": {"X": 1.0},
            "attempts": [
                {"skill": "X", "question": {"question_type": "choice", "correct_answer": "A"}, "user_answer": "A"},
            ],
        })

        assert 0 <= state["mastery_vector"]["X"] <= 1

    @pytest.mark.asyncio
    async def test_mixed_correct_wrong_attempts(self):
        from app.agents.diagnose_agent import DiagnoseAgent

        agent = DiagnoseAgent()
        state = await agent.run({
            "topic": "混合测试",
            "skills": ["Y"],
            "prior_mastery": {"Y": 0.5},
            "attempts": [
                {"skill": "Y", "question": {"question_type": "choice", "correct_answer": "A"}, "user_answer": "A"},
                {"skill": "Y", "question": {"question_type": "choice", "correct_answer": "B"}, "user_answer": "X"},
            ],
        })

        assert 0 <= state["mastery_vector"]["Y"] <= 1


class TestGoalAgent:
    @pytest.mark.asyncio
    async def test_fallback_goal(self):
        from app.agents.goal_agent import GoalAgent

        agent = GoalAgent(use_mock_llm=True)
        state = await agent.run({"input": "我想学会 Transformer", "student_profile": {}})

        assert state["goal_title"]
        assert state["target_topic"]
        assert state["target_level"]

    @pytest.mark.asyncio
    async def test_empty_input_produces_fallback(self):
        from app.agents.goal_agent import GoalAgent

        agent = GoalAgent(use_mock_llm=True)
        state = await agent.run({"input": "", "student_profile": {}})

        assert state["goal_title"]
        assert state["target_topic"]


class TestScheduleAgent:
    @pytest.mark.asyncio
    async def test_fallback_schedule(self):
        from app.agents.schedule_agent import ScheduleAgent

        agent = ScheduleAgent(use_mock_llm=True)
        state = await agent.run({
            "goal": {"goal_title": "学会梯度下降", "target_topic": "梯度下降"},
            "decomposition": {
                "macro_topics": [{"name": "梯度下降", "bloom_level": "understand"}],
                "micro_skills": [{"name": "学习率", "bloom_level": "remember"}],
            },
            "student_profile": {},
        })

        assert len(state["steps"]) > 0
        assert state["plan_title"]

    @pytest.mark.asyncio
    async def test_empty_goal_produces_fallback(self):
        from app.agents.schedule_agent import ScheduleAgent

        agent = ScheduleAgent(use_mock_llm=True)
        state = await agent.run({
            "goal": {},
            "decomposition": {},
            "student_profile": {},
        })

        assert len(state["steps"]) > 0

    @pytest.mark.asyncio
    async def test_non_dict_macro_topics_does_not_crash(self):
        from app.agents.schedule_agent import ScheduleAgent

        agent = ScheduleAgent(use_mock_llm=True)
        state = await agent.run({
            "goal": {"goal_title": "测试"},
            "decomposition": {"macro_topics": ["plain_string_instead_of_dict"]},
            "student_profile": {},
        })

        assert "steps" in state


class TestAdjustmentAgent:
    @pytest.mark.asyncio
    async def test_adjustment_adds_reviews_for_weak_skills(self):
        from app.agents.adjustment_agent import AdjustmentAgent

        agent = AdjustmentAgent()
        state = await agent.run({
            "original_plan": {
                "steps": [
                    {"day": 1, "topic": "神经网络", "type": "learn"},
                    {"day": 2, "topic": "反向传播", "type": "learn"},
                ],
                "daily_capacity": 3,
            },
            "mastery_vector": {"神经网络": 0.9, "反向传播": 0.3},
            "days_idle": 5,
            "events": [],
        })

        assert len(state["added_reviews"]) > 0
        assert any(s.get("topic") == "反向传播" for s in state["updated_steps"])

    @pytest.mark.asyncio
    async def test_all_mastered_no_reviews(self):
        from app.agents.adjustment_agent import AdjustmentAgent

        agent = AdjustmentAgent()
        state = await agent.run({
            "original_plan": {
                "steps": [{"day": 1, "topic": "A", "type": "learn"}],
                "daily_capacity": 3,
            },
            "mastery_vector": {"A": 0.95},
            "days_idle": 0,
            "events": [],
        })

        assert len(state["added_reviews"]) == 0

    @pytest.mark.asyncio
    async def test_zero_days_idle_no_warmup(self):
        from app.agents.adjustment_agent import AdjustmentAgent

        agent = AdjustmentAgent()
        state = await agent.run({
            "original_plan": {
                "steps": [{"day": 1, "topic": "A", "type": "learn"}],
                "daily_capacity": 3,
            },
            "mastery_vector": {"A": 0.5},
            "days_idle": 0,
            "events": [],
        })

        assert state["adjustment_reason"] == "根据最新掌握度进行常规微调"


class TestImageAgent:
    @pytest.mark.asyncio
    async def test_fallback_image(self):
        from app.agents.image_agent import ImageAgent

        agent = ImageAgent(use_mock_llm=True)
        state = await agent.run({"topic": "注意力机制", "student_profile": {}})

        assert state["prompt"]
        assert state["style"] in ("diagram", "illustration", "mindmap", "comparison")

    @pytest.mark.asyncio
    async def test_empty_topic_produces_fallback(self):
        from app.agents.image_agent import ImageAgent

        agent = ImageAgent(use_mock_llm=True)
        state = await agent.run({"topic": "", "student_profile": {}})

        assert state["prompt"]
        assert state["style"] == "diagram"


class TestCodeAgentMultiLanguage:
    @pytest.mark.asyncio
    async def test_code_language_propagation(self):
        from app.agents.code_agent import CodeAgent

        agent = CodeAgent(use_mock_llm=True)
        state = await agent.run({"topic": "排序", "code_language": "java", "student_profile": {}})

        blocks = state.get("blocks", [])
        assert any("java" in b.get("heading", "").lower() for b in blocks)

    @pytest.mark.asyncio
    async def test_missing_code_language_defaults_to_python(self):
        from app.agents.code_agent import CodeAgent

        agent = CodeAgent(use_mock_llm=True)
        blocks = agent._render_content("排序", "python", "print(1)", "解释")
        assert "python" in blocks.lower()

    @pytest.mark.asyncio
    async def test_unsupported_language_falls_back(self):
        from app.agents.code_agent import CodeAgent

        agent = CodeAgent(use_mock_llm=True)
        state = await agent.run({"topic": "排序", "code_language": "ruby", "student_profile": {}})

        blocks = state.get("blocks", [])
        assert any("python" in b.get("heading", "").lower() for b in blocks)

    @pytest.mark.asyncio
    async def test_empty_topic_produces_code(self):
        from app.agents.code_agent import CodeAgent

        agent = CodeAgent(use_mock_llm=True)
        state = await agent.run({"topic": "", "code_language": "python", "student_profile": {}})

        blocks = state.get("blocks", [])
        assert len(blocks) > 0


class TestIntentExtractorDiagnose:
    @pytest.mark.asyncio
    async def test_diagnose_intent_recognized(self):
        from app.services.intent_extractor import IntentExtractor

        extractor = IntentExtractor(use_mock=True)
        result = await extractor.extract("帮我诊断一下机器学习的掌握情况")

        assert result.intent == "diagnose"
        assert "topic" in result.params


class TestAutoCenterP1:
    @pytest.mark.asyncio
    async def test_explain_broad_topic_uses_decompose(self):
        from app.agents.decompose_agent import DecomposeAgent
        from app.agents.layered_explain_agent import LayeredExplainAgent
        from app.centers.auto_center import AutoCenter
        from app.centers.schemas import CenterTask

        center = AutoCenter(
            decompose_agent=DecomposeAgent(use_mock_llm=True),
            layered_explain_agent=LayeredExplainAgent(use_mock_llm=True),
        )
        task = CenterTask(
            mode="auto",
            intent="explain",
            input="机器学习是什么",
            params={"topic": "机器学习"},
            context={"student_profile": {}},
        )
        result = await center.execute(task)

        assert result.event_type == "content"
        assert "macro_topics" in result.payload
        assert "intuition_layer" in result.payload

    @pytest.mark.asyncio
    async def test_explain_narrow_topic_skips_decompose(self):
        from app.agents.decompose_agent import DecomposeAgent
        from app.agents.layered_explain_agent import LayeredExplainAgent
        from app.centers.auto_center import AutoCenter
        from app.centers.schemas import CenterTask

        center = AutoCenter(
            decompose_agent=DecomposeAgent(use_mock_llm=True),
            layered_explain_agent=LayeredExplainAgent(use_mock_llm=True),
        )
        task = CenterTask(
            mode="auto",
            intent="explain",
            input="什么是梯度下降的数学推导",
            params={"topic": "梯度下降的数学推导"},
            context={"student_profile": {}},
        )
        result = await center.execute(task)

        assert result.event_type == "content"
        assert result.agent == "LayeredExplainAgent"

    @pytest.mark.asyncio
    async def test_diagnose_routes_to_diagnose_agent(self):
        from app.agents.diagnose_agent import DiagnoseAgent
        from app.centers.auto_center import AutoCenter
        from app.centers.schemas import CenterTask

        center = AutoCenter(diagnose_agent=DiagnoseAgent())
        task = CenterTask(
            mode="auto",
            intent="diagnose",
            input="诊断神经网络掌握情况",
            params={"topic": "神经网络", "skills": ["神经网络"], "attempts": []},
            context={"student_profile": {}},
        )
        result = await center.execute(task)

        assert result.event_type == "content"
        assert "mastery_vector" in result.payload


class TestPlanCenterP1:
    @pytest.mark.asyncio
    async def test_new_plan_pipeline(self):
        from app.agents.decompose_agent import DecomposeAgent
        from app.agents.goal_agent import GoalAgent
        from app.agents.schedule_agent import ScheduleAgent
        from app.centers.plan_center import PlanCenter
        from app.centers.schemas import CenterTask

        center = PlanCenter(
            goal_agent=GoalAgent(use_mock_llm=True),
            decompose_agent=DecomposeAgent(use_mock_llm=True),
            schedule_agent=ScheduleAgent(use_mock_llm=True),
        )
        task = CenterTask(
            mode="plan",
            intent="learning_path",
            input="我想学 Transformer",
            params={"topic": "Transformer"},
            context={"student_profile": {}},
        )
        result = await center.execute(task)

        assert result.event_type == "plan"
        assert "goal" in result.payload
        assert "concept_graph" in result.payload

    @pytest.mark.asyncio
    async def test_adjustment_pipeline(self):
        from app.agents.adjustment_agent import AdjustmentAgent
        from app.centers.plan_center import PlanCenter
        from app.centers.schemas import CenterTask

        center = PlanCenter(adjustment_agent=AdjustmentAgent())
        task = CenterTask(
            mode="plan",
            intent="adjust_plan",
            input="调整计划",
            params={
                "original_plan": {"steps": [{"day": 1, "topic": "A", "type": "learn"}], "daily_capacity": 3},
                "mastery_vector": {"A": 0.3},
                "days_idle": 6,
            },
            context={"student_profile": {}},
        )
        result = await center.execute(task)

        assert result.event_type == "plan"
        assert len(result.payload["updated_steps"]) > 0

    @pytest.mark.asyncio
    async def test_legacy_path_when_no_p1_agents(self):
        from app.centers.plan_center import PlanCenter
        from app.centers.schemas import CenterTask

        center = PlanCenter()
        task = CenterTask(
            mode="plan",
            intent="learning_path",
            input="学习路径",
            params={"topic": "AI基础"},
            context={"student_profile": {}},
        )
        result = await center.execute(task)

        assert result.event_type in ("plan", "inquiry")


class TestRouterDiagnoseMode:
    @pytest.mark.asyncio
    async def test_manual_diagnose_mode(self):
        from app.centers.router_agent import RouterAgent
        from app.services.intent_extractor import IntentExtractor

        router = RouterAgent(intent_extractor=IntentExtractor(use_mock=True))
        plan = await router.route("诊断一下", mode="diagnose")

        assert len(plan.tasks) == 1
        assert plan.tasks[0].intent == "diagnose"
        assert plan.tasks[0].mode == "auto"


class TestDiagnoseParams:
    def test_diagnose_params_includes_prior_mastery_and_attempts(self):
        from app.services.intent_extractor import DiagnoseParams

        params = DiagnoseParams(topic="AI", skills=["A", "B"])
        assert params.prior_mastery == {}
        assert params.attempts == []

        full = DiagnoseParams(
            topic="AI",
            skills=["A"],
            prior_mastery={"A": 0.5},
            attempts=[{"skill": "A", "is_correct": True}],
        )
        assert full.prior_mastery == {"A": 0.5}
        assert len(full.attempts) == 1
