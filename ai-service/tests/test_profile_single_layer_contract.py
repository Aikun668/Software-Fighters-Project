"""P3-B3b：画像双层图 → 单层图 的契约。

**合并前**：`ProfileWorkflow`（5 节点：extract/merge/completeness_check/response/complete）
逐节点转发 `ProfileAgent` 的同名节点；而 `ProfileAgent` 自己的图是
extract → **semantic_judge** → merge → **audit** → respond。
两者节点集不一致 → 内层的 `semantic_judge`（语义去重）与 `audit`（画像审计）
**在生产路径从未执行**：设计好的画像质量能力被静默跳过。

**合并后**：外层只剩 3 个节点，`pipeline` 委托 `ProfileAgent.run()` —— 唯一管线。

本文件锁定：

| 编号 | 断言 |
|---|---|
| `PS-A01` | 外层图**运行时**节点集 == {pipeline, completeness_check, complete} |
| `PS-A02` | 内层（唯一管线）**运行时**包含 `semantic_judge` / `audit` —— 能力不再被绕过 |
| `PS-A03` | 外层不再有 `_extract_node` / `_merge_node` / `_response_node` 转发节点 |
| `PS-A04` | 行为级：`pipeline` 确实委托 `ProfileAgent.run()`；不完整分支原样返回管线产出 |
| `PS-A05` | 行为级：完整分支由 `complete` 覆盖为固定文案（路由语义不变） |

> `PS-A04/A05` 用 spy 替换 `profile_agent.run`，故不触库、不触网。
"""

import ast
from pathlib import Path

import pytest

from app.agents.profile_agent import ProfileAgent
from app.workflows.profile_workflow import ProfileWorkflow

AI_SERVICE_DIR = Path(__file__).resolve().parent.parent
WORKFLOW_SOURCE = AI_SERVICE_DIR / "app/workflows/profile_workflow.py"


def _graph_node_names(compiled) -> set[str]:
    """编译图 → 节点名集合（langgraph 的 `get_graph()` 暴露 `nodes` 映射）。"""
    inner = compiled.get_graph()
    return set(getattr(inner, "nodes", {}))


def _full_profile() -> dict:
    """6 维全满 → `completeness_check` 判「完整」。"""
    return {
        "knowledge_base": 70,
        "cognitive_style": "visual",
        "learning_goal": "master ML",
        "weak_points": ["math"],
        "learning_pace": "fast",
        "interest_direction": ["NLP"],
    }


def _incomplete_profile() -> dict:
    """仅 2 维有值 → 判「不完整」。"""
    return {"knowledge_base": 50, "cognitive_style": "visual"}


class TestSingleLayerGraph:

    def test_ps_a01_outer_graph_has_three_nodes(self):
        """外层图只剩 pipeline / completeness_check / complete。"""
        workflow = ProfileWorkflow(use_mock=True)

        nodes = _graph_node_names(workflow.graph)

        assert {"pipeline", "completeness_check", "complete"} <= nodes, (
            f"缺少节点：{nodes}"
        )
        for stale in ("extract", "merge", "response"):
            assert stale not in nodes, f"旧的转发节点 {stale} 仍在图里：{nodes}"

    def test_ps_a02_inner_pipeline_contains_quality_nodes(self):
        """唯一管线必须包含 `semantic_judge` / `audit`（合并的核心收益）。"""
        workflow = ProfileWorkflow(use_mock=True)

        nodes = _graph_node_names(workflow.profile_agent._compiled_graph)

        assert "semantic_judge" in nodes, f"语义去重节点被绕过：{nodes}"
        assert "audit" in nodes, f"画像审计节点被绕过：{nodes}"

    def test_ps_a03_forwarding_nodes_removed(self):
        """外层不再保留逐节点转发函数（否则又是两层）。"""
        source = WORKFLOW_SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        defined = {
            node.name
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            for node in node.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        stale = [n for n in ("_extract_node", "_merge_node", "_response_node") if n in defined]
        assert stale == [], f"转发节点仍存在：{stale}"


class TestPipelineDelegation:

    @pytest.mark.asyncio
    async def test_ps_a04_pipeline_delegates_to_agent_run(self):
        """`pipeline` 必须委托 `ProfileAgent.run()`；不完整分支原样返回其产出。"""
        workflow = ProfileWorkflow(use_mock=True)
        captured: list[dict] = []

        async def _fake_run(state):
            captured.append(dict(state))
            return {"response": "请问你更习惯看代码还是看图示？", "current_profile": _incomplete_profile()}

        workflow.profile_agent.run = _fake_run  # type: ignore[method-assign]

        result = await workflow.run({
            "messages": [{"role": "user", "content": "我在学机器学习"}],
            "user_id": 1,
            "current_profile": {},
        })

        assert captured, "pipeline 未委托 ProfileAgent.run —— 双层图又被拆回来了"
        assert result["response"] == "请问你更习惯看代码还是看图示？"
        assert result["profile_complete"] is False

    @pytest.mark.asyncio
    async def test_ps_a05_complete_branch_overrides_with_canned_message(self):
        """画像完整时，`complete` 的固定文案覆盖管线产出的 response。"""
        workflow = ProfileWorkflow(use_mock=True)

        async def _fake_run(state):
            return {"response": "（管线产出的追问，应被覆盖）", "current_profile": _full_profile()}

        workflow.profile_agent.run = _fake_run  # type: ignore[method-assign]

        result = await workflow.run({
            "messages": [{"role": "user", "content": "继续"}],
            "user_id": 1,
            "current_profile": _full_profile(),
        })

        assert result["profile_complete"] is True
        assert "太棒了" in result["response"], f"完整分支文案异常：{result['response']!r}"
        assert "（管线产出的追问，应被覆盖）" not in result["response"]


class TestQualityNodesActuallyRun:
    """⚠️ 本轮最关键的证据：judge / audit **真的会执行**。

    字节存证覆盖不到这里 —— `acceptance/harness/sse_all_endpoints.py` 的
    `profile_chat` 用例 stub 掉了工作流，所以合并前后 55 条存证完全一致，
    **不能**用来证明"没变行为"。真实的可达性证据由本类给出。
    """

    def _spy_agent(self, order: list[str]) -> ProfileAgent:
        """把 5 个节点全换成**不触网不触库**的 spy，再重新编译图以捕获 spy。"""
        agent = ProfileAgent(use_mock_llm=True)

        def _spy(name):
            async def _node(state):
                order.append(name)
                return {}
            return _node

        for name in ("extract", "merge", "respond"):
            setattr(agent, name, _spy(name))
        agent._semantic_judge_node = _spy("semantic_judge")
        agent._audit_node = _spy("audit")
        agent._compiled_graph = agent.build_graph()  # 重新编译，捕获 spy
        return agent

    @pytest.mark.asyncio
    async def test_ps_a06_agent_pipeline_runs_five_nodes_in_order(self):
        order: list[str] = []
        agent = self._spy_agent(order)

        await agent.run({"messages": [{"role": "user", "content": "hi"}], "user_id": 1})

        assert order == ["extract", "semantic_judge", "merge", "audit", "respond"], (
            f"管线节点顺序异常：{order}"
        )

    @pytest.mark.asyncio
    async def test_ps_a07_workflow_path_reaches_quality_nodes(self):
        """**端到端**：走 `ProfileWorkflow.run()` 也能到 judge / audit。

        合并前这条路径只有 extract → merge → completeness_check；
        本用例会因 order 里缺 `semantic_judge` / `audit` 而红。
        """
        workflow = ProfileWorkflow(use_mock=True)
        order: list[str] = []
        workflow.profile_agent = self._spy_agent(order)

        await workflow.run({
            "messages": [{"role": "user", "content": "hi"}],
            "user_id": 1,
            "current_profile": {},
        })

        assert "semantic_judge" in order, f"生产路径未执行语义去重：{order}"
        assert "audit" in order, f"生产路径未执行画像审计：{order}"
        assert order.index("semantic_judge") < order.index("merge") < order.index("audit")
