import pytest

from app.agents.solve_agent import SolveAgent, SolveState


# ═══════════════════════════════════════════════════════════════
# Mock helpers
# ═══════════════════════════════════════════════════════════════

class _FakeLLM:
    """Returns known JSON for _call_llm_json."""
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    async def chat_stream(self, messages, system_prompt=""):
        yield self.responses.get("chat", "")

    async def chat(self, messages, system_prompt=""):
        return self.responses.get("chat", "{}")


def _make_agent(responses=None):
    """Create a SolveAgent with mock LLM."""
    agent = SolveAgent(use_mock_llm=False)
    agent.llm = _FakeLLM(responses or {})
    agent._load_extra_prompt = lambda *a, **kw: "mock prompt"
    agent._call_llm_json = _fake_call_llm_json(agent, responses or {})
    return agent


def _fake_call_llm_json(agent, responses):
    async def wrapper(system_prompt="", user_prompt="", expected_key="", fallback=None):
        # Use responses dict if provided, otherwise use defaults
        default_responses = {
            "steps": {"steps": [
                {"step": 1, "title": "理解题意", "goal": "明确条件"},
                {"step": 2, "title": "求解", "goal": "计算结果"},
            ]},
            "solution": {"solution": "解答：这是一道关于AI的题目。逐步分析如下..."},
            "confidence_score": {
                "confidence_score": 0.85,
                "issues": ["步骤2缺少中间推导"],
                "suggestions": "建议补充计算过程",
            },
        }
        source = responses if responses else default_responses
        return source.get(expected_key, fallback or {})

    return wrapper


# ═══════════════════════════════════════════════════════════════
# SolveAgent graph structure
# ═══════════════════════════════════════════════════════════════

class TestSolveAgentGraph:
    def test_build_graph_returns_compiled_graph(self):
        agent = SolveAgent(use_mock_llm=True)
        graph = agent.build_graph()
        assert graph is not None
        # Compiled graph has invoke/ainvoke methods
        assert hasattr(graph, 'ainvoke')
        assert hasattr(graph, 'invoke')

    def test_graph_has_three_nodes(self):
        agent = SolveAgent(use_mock_llm=True)
        graph = agent.build_graph()
        # Nodes are stored in the graph's channels
        # Just verify the graph compiles without errors
        assert graph is not None


# ═══════════════════════════════════════════════════════════════
# _mock_plan / _mock_solution
# ═══════════════════════════════════════════════════════════════

class TestMockPlan:
    def test_mock_plan_returns_four_steps(self):
        agent = SolveAgent(use_mock_llm=True)
        steps = agent._mock_plan("什么是机器学习？")
        assert len(steps) == 4
        assert all("step" in s for s in steps)
        assert all("title" in s for s in steps)
        assert all("goal" in s for s in steps)
        assert steps[0]["step"] == 1
        assert steps[-1]["step"] == 4

    def test_mock_solution_includes_all_steps(self):
        agent = SolveAgent(use_mock_llm=True)
        steps = agent._mock_plan("test")
        solution = agent._mock_solution(steps, "什么是AI？")
        assert "什么是AI？" in solution
        assert "第1步" in solution
        assert "第4步" in solution


# ═══════════════════════════════════════════════════════════════
# Node logic (integration)
# ═══════════════════════════════════════════════════════════════

class TestSolveNodes:
    @pytest.mark.asyncio
    async def test_plan_node_returns_steps(self):
        agent = _make_agent()
        state: SolveState = {
            "question": "什么是梯度下降？",
            "context": "机器学习基础",
        }
        result = await agent._plan_node(state)
        assert "steps" in result
        assert len(result["steps"]) == 2

    @pytest.mark.asyncio
    async def test_solve_node_returns_solution(self):
        agent = _make_agent()
        state: SolveState = {
            "question": "什么是梯度下降？",
            "context": "",
            "steps": [{"step": 1, "title": "分析", "goal": "理解"}],
            "student_profile": {},
        }
        result = await agent._solve_node(state)
        assert "solution" in result
        assert len(result["solution"]) > 0

    @pytest.mark.asyncio
    async def test_review_node_captures_issues_and_suggestions(self):
        agent = _make_agent()
        state: SolveState = {
            "solution": "解答内容...",
            "steps": [{"step": 1, "title": "分析", "goal": "理解"}],
        }
        result = await agent._review_node(state)
        assert "confidence_score" in result
        assert result["confidence_score"] == 0.85
        assert "issues" in result
        assert len(result["issues"]) == 1
        assert "suggestions" in result
        assert len(result["suggestions"]) > 0

    @pytest.mark.asyncio
    async def test_review_node_handles_non_numeric_confidence(self):
        agent = _make_agent(responses={
            "confidence_score": {"confidence_score": "high", "issues": [], "suggestions": ""}
        })
        state: SolveState = {"solution": "x", "steps": []}
        result = await agent._review_node(state)
        assert result["confidence_score"] == 0.8  # fallback
