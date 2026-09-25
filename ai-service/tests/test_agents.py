import pytest
from unittest.mock import patch, MagicMock

from app.agents.profile_agent import ProfileAgent
from app.agents.content_agent import ContentAgent
from app.agents.exercise_agent import ExerciseAgent
from app.agents.path_agent import PathAgent
from app.agents.tutor_agent import TutorAgent


def _make_mock_kb():
    kb = MagicMock()
    kb.is_empty.return_value = True
    kb.format_context.return_value = ""
    kb.search.return_value = []
    return kb


class TestProfileAgent:
    @pytest.fixture
    def agent(self):
        return ProfileAgent()

    @pytest.mark.asyncio
    async def test_initialization(self, agent):
        assert agent.agent_name == "profile_agent"
        assert agent.use_mock_llm is False

    @pytest.mark.asyncio
    async def test_run_extracts_profile(self, agent):
        state = await agent.run({
            "messages": [{"role": "user", "content": "我数学基础不好，想学深度学习"}],
            "user_id": 1,
            "current_profile": {},
        })
        assert "response" in state
        assert isinstance(state["response"], str)

    @pytest.mark.asyncio
    async def test_run_with_existing_profile(self, agent):
        state = await agent.run({
            "messages": [{"role": "user", "content": "我 Python 也不太会"}],
            "user_id": 1,
            "current_profile": {"knowledge_base": 30},
        })
        assert "response" in state
        assert "current_profile" in state


class TestContentAgent:
    @pytest.fixture
    def agent(self):
        return ContentAgent()

    @pytest.mark.asyncio
    async def test_initialization(self, agent):
        assert agent.agent_name == "content_agent"

    # P3-C 收口：本用例断言「真实产出 content_blocks」，mock LLM 对 ContentAgent
    # 返回的 JSON 形状不兼容（mock 给 `updates`，期望 `subsections`），故只能真跑。
    @pytest.mark.real_llm
    @pytest.mark.asyncio
    async def test_run_generates_content(self, agent):
        state = await agent.run({
            "topic": "Python基础",
            "student_profile": {"knowledge_base": 40},
        })
        assert "content_blocks" in state
        assert isinstance(state["content_blocks"], list)
        assert len(state["content_blocks"]) > 0

    @pytest.mark.real_llm
    @pytest.mark.asyncio
    async def test_content_block_structure(self, agent):
        state = await agent.run({
            "topic": "深度学习基础概念",
            "student_profile": {},
        })
        blocks = state.get("content_blocks", [])
        assert len(blocks) > 0
        for block in blocks:
            assert "type" in block


class TestExerciseAgent:
    @pytest.fixture
    def agent(self):
        return ExerciseAgent()

    @pytest.mark.asyncio
    async def test_initialization(self, agent):
        assert agent.agent_name == "exercise_agent"

    @pytest.mark.asyncio
    async def test_run_generates_questions(self, agent):
        state = await agent.run({
            "topic": "决策树",
            "count": 3,
            "difficulty": "medium",
            "student_profile": {},
        })
        assert "questions" in state
        assert len(state["questions"]) >= 1

    @pytest.mark.asyncio
    async def test_question_structure(self, agent):
        state = await agent.run({
            "topic": "支持向量机",
            "count": 1,
            "difficulty": "easy",
            "student_profile": {},
        })
        questions = state.get("questions", [])
        assert len(questions) > 0
        q = questions[0]
        assert "question_type" in q
        assert "question" in q

    @pytest.mark.asyncio
    async def test_run_with_weak_points(self, agent):
        state = await agent.run({
            "topic": "机器学习",
            "count": 2,
            "difficulty": "hard",
            "student_profile": {"weak_points": ["梯度下降"]},
        })
        assert len(state["questions"]) >= 1


class TestPathAgent:
    @pytest.fixture
    def agent(self):
        return PathAgent()

    @pytest.mark.asyncio
    async def test_initialization(self, agent):
        assert agent.agent_name == "path_agent"

    @pytest.mark.asyncio
    async def test_run_generates_path(self, agent):
        state = await agent.run({
            "student_id": "test_1",
            "student_profile": {"knowledge_base": 50},
        })
        assert "steps" in state
        assert len(state["steps"]) > 0
        assert "concept_graph" in state

    @pytest.mark.asyncio
    async def test_step_structure(self, agent):
        state = await agent.run({
            "student_id": "test_1",
            "student_profile": {"knowledge_base": 50},
        })
        steps = state.get("steps", [])
        assert len(steps) > 0
        step = steps[0]
        assert "topic" in step

    @pytest.mark.asyncio
    async def test_different_knowledge_levels(self, agent):
        for kb in [20, 50, 80]:
            state = await agent.run({
                "student_id": "test_1",
                "student_profile": {"knowledge_base": kb},
            })
            assert len(state["steps"]) > 0

    @pytest.mark.asyncio
    async def test_concept_graph_structure(self, agent):
        state = await agent.run({
            "student_id": "test_1",
            "student_profile": {"knowledge_base": 50},
        })
        graph = state.get("concept_graph", {})
        assert isinstance(graph, dict)


class TestTutorAgent:
    @pytest.fixture
    def agent(self):
        return TutorAgent()

    @pytest.mark.asyncio
    async def test_initialization(self, agent):
        assert agent.agent_name == "tutor_agent"

    @pytest.mark.real_llm
    @pytest.mark.asyncio
    async def test_run_responds(self, agent):
        with patch("app.agents.tutor_agent.get_kb", return_value=_make_mock_kb()):
            state = await agent.run({
                "messages": [{"role": "user", "content": "什么是CNN？"}],
                "user_id": 1,
                "student_profile": {"knowledge_base": 40},
            })
        assert "response" in state
        assert isinstance(state["response"], str)
        assert len(state["response"]) > 0

    @pytest.mark.asyncio
    async def test_knowledge_context(self, agent):
        with patch("app.agents.tutor_agent.get_kb", return_value=_make_mock_kb()):
            state = await agent.run({
                "messages": [{"role": "user", "content": "测试"}],
                "user_id": 1,
                "student_profile": {},
            })
        assert "knowledge_context" in state
        assert isinstance(state["knowledge_context"], str)
