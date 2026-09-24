"""Tests for orchestration layer: AgentTurnSummary, AgentBus, Director"""

import pytest

from app.orchestration.agent_turn_summary import AgentTurnSummary
from app.orchestration.agent_bus import AgentBus
from app.orchestration.resource_selector import ResourceAgentSelector, RouteDecision


class TestAgentTurnSummary:
    def test_empty_summary(self):
        summary = AgentTurnSummary(agent_name="TestAgent", topic="")
        assert summary.covered_concepts == []
        assert summary.generation_intent == ""

    def test_to_dict_and_from_dict_roundtrip(self):
        original = AgentTurnSummary(
            agent_name="ContentAgent",
            topic="机器学习",
            covered_concepts=["监督学习", "无监督学习"],
            generation_intent="讲解机器学习的核心概念",
            avoid_duplicating=["CNN架构", "RNN原理"],
            output_metrics={"block_count": 5, "word_count": 1200},
        )
        d = original.to_dict()
        restored = AgentTurnSummary.from_dict(d)
        assert restored.agent_name == original.agent_name
        assert restored.topic == original.topic
        assert restored.covered_concepts == original.covered_concepts
        assert restored.generation_intent == original.generation_intent
        assert restored.avoid_duplicating == original.avoid_duplicating
        assert restored.output_metrics == original.output_metrics

    def test_build_peer_context_empty(self):
        result = AgentTurnSummary.build_peer_context_section(
            "TestAgent", []
        )
        assert result == ""

    def test_build_peer_context_excludes_self(self):
        summaries = [
            AgentTurnSummary(
                agent_name="CodeAgent",
                topic="Python",
                covered_concepts=["函数", "类"],
                generation_intent="生成Python代码示例",
            )
        ]
        result = AgentTurnSummary.build_peer_context_section(
            "CodeAgent", summaries
        )
        assert result == ""

    def test_build_peer_context_includes_others(self):
        summaries = [
            AgentTurnSummary(
                agent_name="ContentAgent",
                topic="机器学习",
                covered_concepts=["监督学习", "无监督学习", "强化学习"],
                generation_intent="讲解机器学习核心概念",
                avoid_duplicating=["CNN", "RNN"],
            ),
            AgentTurnSummary(
                agent_name="MindMapAgent",
                topic="机器学习",
                covered_concepts=["概念关系图"],
                generation_intent="生成知识结构思维导图",
            ),
        ]
        result = AgentTurnSummary.build_peer_context_section(
            "CodeAgent", summaries
        )
        # For CodeAgent, both other agents should appear
        assert "ContentAgent" in result
        assert "MindMapAgent" in result
        assert "请勿重复" in result

    def test_build_peer_context_limits_items(self):
        summaries = [
            AgentTurnSummary(
                agent_name=f"Agent{i}",
                topic="Test",
                covered_concepts=[f"concept{i}"],
                generation_intent=f"intent {i}",
            )
            for i in range(10)
        ]
        result = AgentTurnSummary.build_peer_context_section(
            "OtherAgent", summaries, max_items=3
        )
        lines = result.split("\n")
        agent_lines = [l for l in lines if l.strip().startswith(("1.", "2.", "3.", "4."))]
        assert len(agent_lines) <= 5  # 3 items with 2 lines each max

    def test_from_dict_partial(self):
        s = AgentTurnSummary.from_dict({"agent_name": "Test", "topic": "x"})
        assert s.agent_name == "Test"
        assert s.topic == "x"
        assert s.covered_concepts == []


class TestAgentBus:
    def test_empty_bus(self):
        bus = AgentBus()
        assert len(bus) == 0
        assert bus.get_peer_context("any") == ""

    def test_submit_and_retrieve(self):
        bus = AgentBus()
        bus.submit(
            AgentTurnSummary(
                agent_name="A", topic="T", covered_concepts=["C1"]
            )
        )
        bus.submit(
            AgentTurnSummary(
                agent_name="B", topic="T", covered_concepts=["C2"]
            )
        )
        assert len(bus) == 2

    def test_get_peer_context_for_agent(self):
        bus = AgentBus()
        bus.submit(
            AgentTurnSummary(
                agent_name="AlphaAgent", topic="Test",
                covered_concepts=["X"], generation_intent="do X",
            )
        )
        bus.submit(
            AgentTurnSummary(
                agent_name="BetaAgent", topic="Test",
                covered_concepts=["Y"], generation_intent="do Y",
            )
        )
        ctx_alpha = bus.get_peer_context("AlphaAgent")
        assert "BetaAgent" in ctx_alpha
        assert "AlphaAgent" not in ctx_alpha

    def test_clear_resets_bus(self):
        bus = AgentBus()
        bus.submit(
            AgentTurnSummary(
                agent_name="A", topic="T", covered_concepts=["C"]
            )
        )
        bus.clear()
        assert len(bus) == 0
        assert bus.get_all_summaries() == []

    def test_get_all_summaries_returns_copy(self):
        bus = AgentBus()
        s = AgentTurnSummary(agent_name="A", topic="T")
        bus.submit(s)
        copies = bus.get_all_summaries()
        copies.clear()
        assert len(bus) == 1


class TestDirector:
    @pytest.mark.asyncio
    async def test_route_returns_route_decision(self):
        director = ResourceAgentSelector()
        decision = await director.route("Python基础")
        assert isinstance(decision, RouteDecision)
        assert decision.agent_name in ("content", "code", "mindmap", "project", "flashcard", "interactive_diagram")
        assert decision.strategy in ("rule", "llm")

    @pytest.mark.asyncio
    async def test_rule_route_code_topic(self):
        director = ResourceAgentSelector()
        decision = await director.route("怎么写一个排序算法的代码示例")
        assert decision.strategy == "rule"
        assert decision.agent_name == "code"

    @pytest.mark.asyncio
    async def test_rule_route_theory_topic(self):
        director = ResourceAgentSelector()
        decision = await director.route("机器学习理论概述")
        assert decision.agent_name in ("content", "mindmap")

    @pytest.mark.asyncio
    async def test_rule_route_ml_topic(self):
        director = ResourceAgentSelector()
        decision = await director.route("深度学习与神经网络代码")
        assert decision.agent_name in ("code", "content")

    @pytest.mark.asyncio
    async def test_rule_route_project_topic(self):
        director = ResourceAgentSelector()
        decision = await director.route("从零搭建一个CNN图像分类项目")
        assert decision.agent_name == "project"

    @pytest.mark.asyncio
    async def test_rule_route_mindmap_topic(self):
        director = ResourceAgentSelector()
        decision = await director.route("梳理一下机器学习的知识框架")
        assert decision.agent_name == "mindmap"

    @pytest.mark.asyncio
    async def test_rule_route_flashcard_topic(self):
        director = ResourceAgentSelector()
        decision = await director.route("背一下反向传播的核心要点")
        assert decision.agent_name == "flashcard"

    @pytest.mark.asyncio
    async def test_rule_route_interactive_diagram_topic(self):
        director = ResourceAgentSelector()
        decision = await director.route("CNN架构的动态可视化演示")
        assert decision.agent_name == "interactive_diagram"

    @pytest.mark.asyncio
    async def test_resource_type_direct_route(self):
        director = ResourceAgentSelector()
        decision = await director.route("任意主题", resource_type="code")
        assert decision.agent_name == "code"
        assert decision.strategy == "type_direct"

    @pytest.mark.asyncio
    async def test_resource_type_direct_route_project(self):
        director = ResourceAgentSelector()
        decision = await director.route("随便什么", resource_type="project")
        assert decision.agent_name == "project"
        assert decision.strategy == "type_direct"

    @pytest.mark.asyncio
    async def test_comparison_sub_type_detected(self):
        director = ResourceAgentSelector()
        decision = await director.route("对比一下CNN和RNN的区别")
        assert decision.sub_type == "comparison"

    @pytest.mark.asyncio
    async def test_diagnosis_sub_type_detected(self):
        director = ResourceAgentSelector()
        decision = await director.route("这个bug怎么排查和修复")
        assert decision.sub_type == "diagnosis"

    @pytest.mark.asyncio
    async def test_default_agent_is_content(self):
        director = ResourceAgentSelector()
        decision = await director.route("xyzzy_unmatched_abc")
        assert decision.agent_name == "content"


class TestRouteDecision:
    def test_default_values(self):
        rd = RouteDecision()
        assert rd.agent_name == "content"
        assert rd.rationale == ""
        assert rd.strategy == ""

    def test_with_agent(self):
        rd = RouteDecision(
            agent_name="code",
            rationale="test",
            strategy="rule",
        )
        assert rd.agent_name == "code"
        assert rd.strategy == "rule"

    def test_with_sub_type(self):
        rd = RouteDecision(
            agent_name="content",
            sub_type="comparison",
            rationale="对比分析",
            strategy="rule",
        )
        assert rd.sub_type == "comparison"


class TestDirectorLLMRoute:
    """LLM fallback 路由路径测试"""

    @pytest.mark.asyncio
    async def test_llm_route_triggered_for_unknown_topic(self):
        """无关键词匹配的 topic 触发 LLM 路由"""
        director = ResourceAgentSelector()
        decision = await director.route("量子计算与量子信息")
        assert isinstance(decision, RouteDecision)
        assert decision.agent_name in ("content", "code", "mindmap", "project", "flashcard", "interactive_diagram")

    @pytest.mark.asyncio
    async def test_llm_route_fallback_on_error(self):
        """LLM 路由失败时回退到默认 Agent"""
        director = ResourceAgentSelector()
        decision = await director.route("xyzzy_unmatched_abc")
        assert isinstance(decision, RouteDecision)
        assert decision.agent_name == "content"


class TestDirectorLLMRouteEdgeCases:
    """LLM 路由边界情况"""

    @pytest.mark.asyncio
    async def test_llm_route_for_unknown_topic_returns_default(self):
        """未匹配任何关键词时走 LLM 路由"""
        director = ResourceAgentSelector()
        decision = await director.route("xyzzy_unmatched_topic_abc")
        assert decision.agent_name in ("content", "code", "mindmap", "project", "flashcard", "interactive_diagram")

    @pytest.mark.asyncio
    async def test_llm_route_with_empty_topic(self):
        """空 topic 的边界情况"""
        director = ResourceAgentSelector()
        decision = await director.route("")
        assert decision.agent_name == "content"

    @pytest.mark.asyncio
    async def test_llm_route_non_ascii_topic(self):
        """非 ASCII topic（中文）"""
        director = ResourceAgentSelector()
        decision = await director.route("机器学习")
        assert decision.strategy == "rule"  # 关键词命中
        assert decision.agent_name in ("content", "code")


class TestContentAgentTurnSummary:
    """ContentAgent.create_turn_summary override 测试"""

    def test_extracts_concepts_from_outline_in_state(self):
        from app.agents.content_agent import ContentAgent

        agent = ContentAgent()
        state = {
            "topic": "机器学习",
            "outline": {
                "subsections": [
                    {"heading": "监督学习", "role": "core"},
                    {"heading": "无监督学习", "role": "core"},
                    {"heading": "强化学习", "role": "application"},
                ],
            },
        }
        output = {
            "content_blocks": [
                {"type": "section", "heading": "监督学习", "content": "..."},
                {"type": "section", "heading": "无监督学习", "content": "..."},
            ],
        }

        summary = agent.create_turn_summary(state, output)
        assert summary.agent_name == "ContentAgent"
        assert summary.topic == "机器学习"
        assert "监督学习" in summary.covered_concepts
        assert "无监督学习" in summary.covered_concepts
        assert len(summary.avoid_duplicating) > 0
        assert summary.output_metrics.get("block_count") == 2

    def test_falls_back_to_content_blocks_when_no_outline(self):
        from app.agents.content_agent import ContentAgent

        agent = ContentAgent()
        state = {"topic": "Python", "outline": {}}
        output = {
            "content_blocks": [
                {"type": "section", "heading": "变量与类型", "content": "..."},
                {"type": "section", "heading": "函数定义", "content": "..."},
            ],
        }

        summary = agent.create_turn_summary(state, output)
        assert summary.topic == "Python"
        assert len(summary.covered_concepts) > 0


class TestDirectorThreshold:
    """Director 基础配置验证"""

    def test_supported_agents_exist(self):
        director = ResourceAgentSelector()
        from app.orchestration.resource_selector import SUPPORTED_AGENTS
        assert "content" in SUPPORTED_AGENTS
        assert "code" in SUPPORTED_AGENTS
        assert "interactive_diagram" in SUPPORTED_AGENTS
        assert "project" in SUPPORTED_AGENTS
        assert "mindmap" in SUPPORTED_AGENTS
        assert "flashcard" in SUPPORTED_AGENTS
        assert len(SUPPORTED_AGENTS) == 6


class TestResourceGenConfig:
    """资源生成配置验证"""

    def test_agent_labels_exist(self):
        from app.workflows.resource_gen import AGENT_LABELS

        assert "content" in AGENT_LABELS
        assert "code" in AGENT_LABELS
        assert "interactive_diagram" in AGENT_LABELS
        assert "project" in AGENT_LABELS
        assert "mindmap" in AGENT_LABELS
        assert "flashcard" in AGENT_LABELS


# ═══════════════════════════════════════════════════════════════
# Per-Agent Model Selection Tests
# ═══════════════════════════════════════════════════════════════


class TestModelConfig:
    """ModelConfig 数据类验证"""

    def test_default_values(self):
        from app.services.llm_service import ModelConfig

        cfg = ModelConfig()
        assert cfg.model == ""
        assert cfg.temperature == 0.7
        assert cfg.max_tokens == 8192

    def test_custom_values(self):
        from app.services.llm_service import ModelConfig

        cfg = ModelConfig(model="MiniMax-M3", temperature=0.3, max_tokens=4096)
        assert cfg.model == "MiniMax-M3"
        assert cfg.temperature == 0.3
        assert cfg.max_tokens == 4096


class TestAgentModelProfile:
    """AgentModelProfile 角色路由验证"""

    def test_get_plan_returns_plan_when_set(self):
        from app.services.llm_service import AgentModelProfile, ModelConfig

        plan_cfg = ModelConfig(temperature=0.3, max_tokens=1024)
        profile = AgentModelProfile(
            default=ModelConfig(temperature=0.7),
            plan=plan_cfg,
        )
        assert profile.get("plan") is plan_cfg

    def test_get_plan_falls_back_to_default(self):
        from app.services.llm_service import AgentModelProfile, ModelConfig

        profile = AgentModelProfile(default=ModelConfig(temperature=0.7))
        result = profile.get("plan")
        assert result is profile.default

    def test_get_generate_returns_generate_when_set(self):
        from app.services.llm_service import AgentModelProfile, ModelConfig

        gen_cfg = ModelConfig(temperature=0.9)
        profile = AgentModelProfile(
            default=ModelConfig(temperature=0.7),
            generate=gen_cfg,
        )
        assert profile.get("generate") is gen_cfg

    def test_get_unknown_role_falls_back_to_default(self):
        from app.services.llm_service import AgentModelProfile, ModelConfig

        profile = AgentModelProfile(default=ModelConfig(temperature=0.7))
        assert profile.get("review") is profile.default


class TestPresetProfiles:
    """预设 Profile 合理性验证"""

    def test_all_presets_exist(self):
        from app.services import llm_service

        for name in [
            "PROFILE_DIRECTOR",
            "PROFILE_CONTENT",
            "PROFILE_EXERCISE",
            "PROFILE_CODE",
            "PROFILE_MINDMAP",
            "PROFILE_READING",
            "PROFILE_FLASHCARD",
            "PROFILE_INTERACTIVE_DIAGRAM",
            "PROFILE_PROJECT",
        ]:
            assert hasattr(llm_service, name), f"Missing preset: {name}"

    def test_director_profile_uses_zero_temperature(self):
        from app.services.llm_service import PROFILE_DIRECTOR

        assert PROFILE_DIRECTOR.default.temperature == 0.0
        assert PROFILE_DIRECTOR.default.max_tokens <= 512

    def test_content_profile_has_plan_with_lower_temperature(self):
        from app.services.llm_service import PROFILE_CONTENT

        assert PROFILE_CONTENT.plan is not None
        assert PROFILE_CONTENT.plan.temperature < PROFILE_CONTENT.default.temperature

    def test_exercise_profile_has_plan_with_lower_temperature(self):
        from app.services.llm_service import PROFILE_EXERCISE

        assert PROFILE_EXERCISE.plan is not None
        assert PROFILE_EXERCISE.plan.temperature < PROFILE_EXERCISE.default.temperature

    def test_code_profile_temperature_is_moderate(self):
        from app.services.llm_service import PROFILE_CODE

        assert 0.3 <= PROFILE_CODE.default.temperature <= 0.7


class TestBaseAgentWithProfile:
    """BaseAgent 使用 ModelProfile 创建 LLM 验证"""

    def test_agent_with_profile_creates_plan_llm(self):
        from app.services.llm_service import AgentModelProfile, ModelConfig
        from app.agents.code_agent import CodeAgent

        profile = AgentModelProfile(
            default=ModelConfig(temperature=0.5),
            plan=ModelConfig(temperature=0.2, max_tokens=2048),
        )
        agent = CodeAgent(model_profile=profile)
        assert hasattr(agent, "plan_llm")
        assert agent.plan_llm is not None
        assert agent.llm is not agent.plan_llm

    def test_agent_without_profile_has_no_plan_llm(self):
        from app.agents.code_agent import CodeAgent

        agent = CodeAgent()
        # CodeAgent doesn't create plan_llm on its own
        assert not hasattr(agent, "plan_llm")

    def test_agent_without_profile_still_has_default_llm(self):
        from app.agents.reading_agent import ReadingAgent

        agent = ReadingAgent()
        assert agent.llm is not None

    def test_content_agent_profile_overrides_manual_plan_llm(self):
        from app.services.llm_service import AgentModelProfile, ModelConfig
        from app.agents.content_agent import ContentAgent

        profile = AgentModelProfile(
            default=ModelConfig(temperature=0.7, max_tokens=8192),
            plan=ModelConfig(temperature=0.2, max_tokens=2048),
        )
        agent = ContentAgent(model_profile=profile)
        # plan_llm should come from profile, not manual creation
        assert hasattr(agent, "plan_llm")

    def test_exercise_agent_profile_overrides_manual_plan_llm(self):
        from app.services.llm_service import AgentModelProfile, ModelConfig
        from app.agents.exercise_agent import ExerciseAgent

        profile = AgentModelProfile(
            default=ModelConfig(temperature=0.7),
            plan=ModelConfig(temperature=0.1, max_tokens=1024),
        )
        agent = ExerciseAgent(model_profile=profile)
        assert hasattr(agent, "plan_llm")


class TestResourceGenProfiles:
    """ResourceGenWorkflow 中 Agent 使用预设 Profile 验证"""

    def test_workflow_agents_have_profiles(self):
        from app.workflows.resource_gen import ResourceGenWorkflow

        wf = ResourceGenWorkflow()
        assert wf.content_agent._model_profile is not None
        assert wf.code_agent._model_profile is not None
        assert wf.mindmap_agent._model_profile is not None
        assert wf.flashcard_agent._model_profile is not None
        assert wf.project_agent._model_profile is not None
        assert wf.interactive_diagram_agent._model_profile is not None

    def test_workflow_director_has_profile(self):
        from app.workflows.resource_gen import ResourceGenWorkflow

        wf = ResourceGenWorkflow()
        assert wf.selector._model_profile is not None

    def test_workflow_agent_map_covers_all_types(self):
        from app.workflows.resource_gen import ResourceGenWorkflow
        from app.orchestration.resource_selector import SUPPORTED_AGENTS

        wf = ResourceGenWorkflow()
        for agent_name in SUPPORTED_AGENTS:
            assert agent_name in wf._agent_map, f"Missing agent in map: {agent_name}"
            assert wf._agent_map[agent_name] is not None
