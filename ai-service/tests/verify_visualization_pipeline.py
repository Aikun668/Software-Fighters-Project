"""P0-1 + P0-2: 可视化管线验证脚本

验证目标:
- P0-1: AutoCenter._maybe_visualize() 端到端门控逻辑
- P0-2: VisualizationCenter.execute() 三种 intent 管线

纯验证，不改逻辑。使用 AsyncMock 模拟 _call_llm_json 避免真实 LLM 调用。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.visualize.visualize_pipeline import VisualizePipeline, VisualizeResult
from app.centers.auto_center import AutoCenter
from app.centers.schemas import CenterTask
from app.centers.visualization_center import VisualizationCenter


# ── helpers ────────────────────────────────────────────────────

def _analysis(should_visualize=True, render_type="mermaid",
              description="流程图", reasoning="适合可视化", confidence=0.95):
    return {"should_visualize": should_visualize, "render_type": render_type,
            "description": description, "data_description": "", "chart_type": "",
            "visual_elements": [], "reasoning": reasoning, "confidence": confidence}


def _code(code="graph TD\n  A-->B", title="测试图表", notes=""):
    return {"code": code, "title": title, "notes": notes}


def _review(changed=False, optimized_code="", issues=None, suggestions=""):
    return {"changed": changed, "optimized_code": optimized_code,
            "issues": issues or [], "suggestions": suggestions}


# ═════════════════════════════════════════════════════════════════
# P0 核心: VisualizePipeline 三阶段管线
# ═════════════════════════════════════════════════════════════════

class TestVisualizePipeline:
    @pytest.mark.asyncio
    async def test_analysis_says_no_returns_skip(self):
        """Analysis 判定不需要可视化 → 返回 skip"""
        pipeline = VisualizePipeline(use_mock_llm=True)
        with patch.object(pipeline.analysis_agent, "_call_llm_json",
                          AsyncMock(return_value=_analysis(should_visualize=False,
                                                           reasoning="纯文字解释，无需图表"))):
            result = await pipeline.run(question="什么是AI?", answer="AI是人工智能的缩写。")
        assert result.should_visualize is False
        assert "无需图表" in result.reasoning

    @pytest.mark.asyncio
    async def test_code_gen_empty_code_returns_skip(self):
        """CodeGen 返回空代码 → 返回 skip"""
        pipeline = VisualizePipeline(use_mock_llm=True)
        with patch.object(pipeline.analysis_agent, "_call_llm_json",
                          AsyncMock(return_value=_analysis())), \
             patch.object(pipeline.code_generator, "_call_llm_json",
                          AsyncMock(return_value={"code": "", "title": "", "notes": ""})):
            result = await pipeline.run(question="反向传播?", answer="反向传播通过链式法则计算梯度。")
        assert result.should_visualize is False

    @pytest.mark.asyncio
    async def test_full_pipeline_success_mermaid(self):
        """完整三阶段: Analysis→CodeGen→Review, 生成 mermaid 图表"""
        pipeline = VisualizePipeline(use_mock_llm=True)
        code = "graph TD\n  Input-->Hidden-->Output"
        with patch.object(pipeline.analysis_agent, "_call_llm_json",
                          AsyncMock(return_value=_analysis(
                              render_type="mermaid", description="神经网络结构",
                              reasoning="多层结构适合流程图"))), \
             patch.object(pipeline.code_generator, "_call_llm_json",
                          AsyncMock(return_value=_code(code=code, title="神经网络架构"))), \
             patch.object(pipeline.review_agent, "_call_llm_json",
                          AsyncMock(return_value=_review(changed=False))):
            result = await pipeline.run(
                question="神经网络有哪些层?",
                answer="神经网络包含输入层、隐藏层和输出层。",
            )
        assert result.should_visualize is True
        assert result.render_type == "mermaid"
        assert result.code == code
        assert result.title == "神经网络架构"

    @pytest.mark.asyncio
    async def test_review_optimizes_code(self):
        """Review 阶段优化代码 → 返回优化后的代码"""
        pipeline = VisualizePipeline(use_mock_llm=True)
        original = "graph TD\n  A-->B"
        optimized = "graph TD\n  A[输入]-->B[输出]"
        with patch.object(pipeline.analysis_agent, "_call_llm_json",
                          AsyncMock(return_value=_analysis())), \
             patch.object(pipeline.code_generator, "_call_llm_json",
                          AsyncMock(return_value=_code(code=original))), \
             patch.object(pipeline.review_agent, "_call_llm_json",
                          AsyncMock(return_value=_review(
                              changed=True, optimized_code=optimized))):
            result = await pipeline.run(question="流程?", answer="输入到输出的流程。")
        assert result.code == optimized

    @pytest.mark.asyncio
    async def test_analysis_exception_propagates(self):
        """Analysis 阶段异常 → 向上传播"""
        pipeline = VisualizePipeline(use_mock_llm=True)
        with patch.object(pipeline.analysis_agent, "_call_llm_json",
                          AsyncMock(side_effect=RuntimeError("LLM timeout"))):
            with pytest.raises(RuntimeError):
                await pipeline.run(question="test?", answer="test answer.")

    @pytest.mark.asyncio
    async def test_codegen_exception_propagates(self):
        """CodeGen 阶段异常 → 向上传播"""
        pipeline = VisualizePipeline(use_mock_llm=True)
        with patch.object(pipeline.analysis_agent, "_call_llm_json",
                          AsyncMock(return_value=_analysis())), \
             patch.object(pipeline.code_generator, "_call_llm_json",
                          AsyncMock(side_effect=RuntimeError("LLM timeout"))):
            with pytest.raises(RuntimeError):
                await pipeline.run(question="test?", answer="test answer.")

    @pytest.mark.asyncio
    async def test_review_exception_propagates(self):
        """Review 阶段异常 → 向上传播"""
        pipeline = VisualizePipeline(use_mock_llm=True)
        with patch.object(pipeline.analysis_agent, "_call_llm_json",
                          AsyncMock(return_value=_analysis())), \
             patch.object(pipeline.code_generator, "_call_llm_json",
                          AsyncMock(return_value=_code())), \
             patch.object(pipeline.review_agent, "_call_llm_json",
                          AsyncMock(side_effect=RuntimeError("LLM timeout"))):
            with pytest.raises(RuntimeError):
                await pipeline.run(question="test?", answer="test answer.")

    @pytest.mark.asyncio
    async def test_preserves_svg_render_type(self):
        """非 mermaid 类型 (svg) 被正确传递"""
        pipeline = VisualizePipeline(use_mock_llm=True)
        svg_code = "<svg viewBox='0 0 100 100'><circle cx='50' cy='50' r='40'/></svg>"
        with patch.object(pipeline.analysis_agent, "_call_llm_json",
                          AsyncMock(return_value=_analysis(
                              render_type="svg", description="树形图"))), \
             patch.object(pipeline.code_generator, "_call_llm_json",
                          AsyncMock(return_value=_code(
                              code=svg_code, title="决策树"))), \
             patch.object(pipeline.review_agent, "_call_llm_json",
                          AsyncMock(return_value=_review())):
            result = await pipeline.run(
                question="决策树怎么构建?",
                answer="通过信息增益选择特征进行分裂。",
            )
        assert result.render_type == "svg"
        assert result.code == svg_code

    @pytest.mark.asyncio
    async def test_analysis_without_should_visualize_key_defaults_false(self):
        """Analysis 返回缺少 should_visualize 字段 → analysis.get 返回 None,
        falsy → 走 skip 路径"""
        pipeline = VisualizePipeline(use_mock_llm=True)
        with patch.object(pipeline.analysis_agent, "_call_llm_json",
                          AsyncMock(return_value={"render_type": "mermaid"})):
            result = await pipeline.run(question="test?", answer="test.")
        assert result.should_visualize is False

    @pytest.mark.asyncio
    async def test_analysis_empty_dict_returns_skip(self):
        """Analysis 返回空 dict → 走 skip"""
        pipeline = VisualizePipeline(use_mock_llm=True)
        with patch.object(pipeline.analysis_agent, "_call_llm_json",
                          AsyncMock(return_value={})):
            result = await pipeline.run(question="test?", answer="test.")
        assert result.should_visualize is False


# ═════════════════════════════════════════════════════════════════
# P0-1: AutoCenter._maybe_visualize() 门控逻辑
# ═════════════════════════════════════════════════════════════════

class TestAutoCenterMaybeVisualize:
    @staticmethod
    def _center(pipeline=None):
        return AutoCenter(visualize_pipeline=pipeline)

    @pytest.mark.asyncio
    async def test_empty_answer_returns_empty(self):
        """空回答 → 跳过，返回 []"""
        result = await self._center()._maybe_visualize(
            messages=[{"role": "user", "content": "什么是AI?"}],
            answer="",
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_whitespace_only_answer_returns_empty(self):
        """纯空白回答 → 跳过"""
        result = await self._center()._maybe_visualize(
            messages=[{"role": "user", "content": "test"}],
            answer="   \n  ",
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_no_user_message_returns_empty(self):
        """消息列表中没有用户消息 → 跳过"""
        result = await self._center()._maybe_visualize(
            messages=[{"role": "assistant", "content": "你好"}],
            answer="这是回答",
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_pipeline_should_not_visualize_returns_empty(self):
        """Pipeline 判定不需要图表 → 返回 []"""
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(return_value=VisualizeResult.skip(reason="不需要"))
        result = await self._center(mock_pipeline)._maybe_visualize(
            messages=[{"role": "user", "content": "你好"}],
            answer="你好！有什么可以帮你的?",
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_pipeline_no_code_returns_empty(self):
        """Pipeline should_visualize=True 但 code 为空 → 返回 []"""
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(return_value=VisualizeResult(
            should_visualize=True, render_type="mermaid", code="", title="empty"))
        result = await self._center(mock_pipeline)._maybe_visualize(
            messages=[{"role": "user", "content": "解释神经网络"}],
            answer="神经网络是通过...",
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_successful_visualization_returns_block(self):
        """Pipeline 成功 → 返回可视化 block"""
        mock_pipeline = MagicMock()
        code = "graph TD\n  A-->B"
        mock_pipeline.run = AsyncMock(return_value=VisualizeResult(
            should_visualize=True, render_type="mermaid",
            code=code, title="测试图", reasoning="适合"))
        messages = [{"role": "user", "content": "反向传播的流程?"}]
        result = await self._center(mock_pipeline)._maybe_visualize(
            messages, "反向传播通过链式法则...",
        )
        assert len(result) == 1
        block = result[0]
        assert block["type"] == "visualization"
        assert block["sub_type"] == "mermaid"
        assert block["heading"] == "测试图"
        assert block["content"] == code
        mock_pipeline.run.assert_awaited_once_with(
            question="反向传播的流程?", answer="反向传播通过链式法则...",
        )

    @pytest.mark.asyncio
    async def test_answer_truncated_to_3000_chars(self):
        """长回答被截断到 3000 字符再传给 pipeline"""
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(return_value=VisualizeResult(
            should_visualize=True, render_type="mermaid",
            code="graph TD\n  A-->B", title="test"))
        long_answer = "X" * 5000
        await self._center(mock_pipeline)._maybe_visualize(
            messages=[{"role": "user", "content": "test"}],
            answer=long_answer,
        )
        call_kwargs = mock_pipeline.run.await_args.kwargs
        assert len(call_kwargs["answer"]) == 3000

    @pytest.mark.asyncio
    async def test_pipeline_exception_non_blocking(self):
        """Pipeline 异常 → 返回 []，不向上传播（非阻塞设计）"""
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(side_effect=RuntimeError("Boom"))
        result = await self._center(mock_pipeline)._maybe_visualize(
            messages=[{"role": "user", "content": "test"}],
            answer="test answer",
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_finds_last_user_message_in_multi_turn(self):
        """多轮对话中正确找到最后一条用户消息"""
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(return_value=VisualizeResult(
            should_visualize=True, render_type="mermaid",
            code="graph TD\n  A-->B", title="t"))
        messages = [
            {"role": "user", "content": "第一个问题"},
            {"role": "assistant", "content": "第一个回答"},
            {"role": "user", "content": "最终问题"},
        ]
        result = await self._center(mock_pipeline)._maybe_visualize(
            messages, "最终回答",
        )
        assert len(result) == 1
        mock_pipeline.run.assert_awaited_once_with(
            question="最终问题", answer="最终回答",
        )

    @pytest.mark.asyncio
    async def test_lazy_pipeline_instantiation(self):
        """未注入 pipeline 时自动创建 VisualizePipeline 实例"""
        center = self._center()  # pipeline=None
        messages = [{"role": "user", "content": "test?"}]
        with patch.object(VisualizePipeline, "run",
                          AsyncMock(return_value=VisualizeResult.skip())):
            result = await center._maybe_visualize(messages, "answer")
        assert result == []


# ═════════════════════════════════════════════════════════════════
# P0-2: VisualizationCenter.execute() 三种 intent 管线
# ═════════════════════════════════════════════════════════════════

class TestVisualizationCenterExecute:
    @staticmethod
    def _center(pipeline=None, mindmap=None, graph_service=None):
        return VisualizationCenter(
            visualize_pipeline=pipeline,
            mindmap_agent=mindmap,
            graph_service=graph_service,
        )

    @staticmethod
    def _task(intent, input_text="test", topic=None, params=None, context=None):
        p = params or {}
        c = context or {}
        if topic:
            p = {**p, "topic": topic}
        return CenterTask(
            mode="visualization", intent=intent, input=input_text,
            params=p, context=c, sequence=1,
        )

    # ── visualize ──

    @pytest.mark.asyncio
    async def test_visualize_intent_success_adds_block(self):
        """intent=visualize + pipeline 成功 → 生成 block"""
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(return_value=VisualizeResult(
            should_visualize=True, render_type="mermaid",
            code="graph TD\n  A-->B", title="测试"))
        task = self._task("visualize", "反向传播的流程", topic="反向传播")
        result = await self._center(pipeline=mock_pipeline).execute(task)
        assert result.event_type == "visualization"
        assert result.payload["type"] == "visualization"
        blocks = result.payload["blocks"]
        assert len(blocks) == 1
        assert blocks[0]["type"] == "mermaid"
        assert blocks[0]["code"] == "graph TD\n  A-->B"

    @pytest.mark.asyncio
    async def test_visualize_intent_pipeline_says_no(self):
        """intent=visualize 但 pipeline 判定不需要 → 无 block"""
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(return_value=VisualizeResult.skip())
        task = self._task("visualize", "简单问候")
        result = await self._center(pipeline=mock_pipeline).execute(task)
        assert result.event_type == "visualization"
        assert result.payload["blocks"] == []

    @pytest.mark.asyncio
    async def test_visualize_uses_input_for_topic(self):
        """无 topic 参数时用 task.input 作为 topic"""
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(return_value=VisualizeResult(
            should_visualize=True, render_type="mermaid",
            code="graph TD", title="t"))
        task = self._task("visualize", "什么是反向传播")
        result = await self._center(pipeline=mock_pipeline).execute(task)
        assert result.payload["topic"] == "什么是反向传播"

    # ── knowledge_graph ──

    @pytest.mark.asyncio
    async def test_knowledge_graph_intent_calls_graph_service(self):
        """intent=knowledge_graph → 调用 graph_service.get_graph"""
        mock_graph = MagicMock()
        mock_graph.get_graph = AsyncMock(return_value={
            "nodes": [{"id": "n1", "name": "AI", "type": "concept"}],
            "edges": [],
        })
        task = self._task("knowledge_graph", params={"course_id": "ai_intro"})
        result = await self._center(graph_service=mock_graph).execute(task)
        blocks = result.payload["blocks"]
        assert len(blocks) == 1
        assert blocks[0]["type"] == "knowledge_graph"
        assert "nodes" in blocks[0]["graph"]
        mock_graph.get_graph.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_knowledge_graph_default_course_id(self):
        """未指定 course_id → 回退到 'ai_intro'"""
        mock_graph = MagicMock()
        mock_graph.get_graph = AsyncMock(return_value={"nodes": [], "edges": []})
        task = self._task("knowledge_graph")
        await self._center(graph_service=mock_graph).execute(task)
        mock_graph.get_graph.assert_awaited_once_with(
            course_id="ai_intro", masteries={},
        )

    @pytest.mark.asyncio
    async def test_knowledge_graph_passes_masteries(self):
        """masteries 从 params 或 context 传递到 graph_service"""
        mock_graph = MagicMock()
        mock_graph.get_graph = AsyncMock(return_value={"nodes": [], "edges": []})
        task = self._task("knowledge_graph", context={
            "masteries": {"ai_overview": 0.9},
        })
        await self._center(graph_service=mock_graph).execute(task)
        mock_graph.get_graph.assert_awaited_once_with(
            course_id="ai_intro", masteries={"ai_overview": 0.9},
        )

    # ── mindmap ──

    @pytest.mark.asyncio
    async def test_mindmap_intent_calls_agent(self):
        """intent=mindmap → 调用 mindmap_agent"""
        mock_mindmap = MagicMock()
        mock_mindmap.run = AsyncMock(return_value={
            "blocks": [{"type": "mindmap", "data": "tree"}],
            "response": "思维导图",
        })
        task = self._task("mindmap", "机器学习", topic="机器学习")
        result = await self._center(mindmap=mock_mindmap).execute(task)
        assert len(result.payload["blocks"]) == 1
        assert result.payload["blocks"][0]["type"] == "mindmap"
        mock_mindmap.run.assert_awaited_once()

    # ── error ──

    @pytest.mark.asyncio
    async def test_exception_returns_error_result(self):
        """管线异常 → 返回 error 类型 CenterResult，不向上传播"""
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(side_effect=RuntimeError("LLM timeout"))
        task = self._task("visualize", "test")
        result = await self._center(pipeline=mock_pipeline).execute(task)
        assert result.event_type == "error"
        assert "可视化生成失败" in result.error
        assert result.agent == "VisualizationCenter"

    # ── cross-intent boundary ──

    @pytest.mark.asyncio
    async def test_visualize_does_not_call_graph_service(self):
        """intent=visualize 不会误调 graph_service"""
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(return_value=VisualizeResult(
            should_visualize=True, render_type="mermaid",
            code="graph TD", title="t"))
        mock_graph = MagicMock()
        task = self._task("visualize", "test")
        result = await self._center(
            pipeline=mock_pipeline, graph_service=mock_graph,
        ).execute(task)
        types = {b.get("type") for b in result.payload["blocks"]}
        assert "knowledge_graph" not in types
        mock_graph.get_graph.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_intent_returns_empty_blocks(self):
        """未知 intent → 不生成任何 block，正常返回空"""
        task = self._task("unknown_intent", "test")
        result = await self._center().execute(task)
        assert result.event_type == "visualization"  # 不会变成 error
        assert result.payload["blocks"] == []


# ═════════════════════════════════════════════════════════════════
# VisualizeResult 数据类
# ═════════════════════════════════════════════════════════════════

class TestVisualizeResult:
    def test_default_is_no_visualize(self):
        r = VisualizeResult()
        assert r.should_visualize is False
        assert r.code == ""
        assert r.render_type == ""

    def test_skip_factory(self):
        r = VisualizeResult.skip(reason="纯文本")
        assert r.should_visualize is False
        assert r.reasoning == "纯文本"

    def test_full_construction(self):
        r = VisualizeResult(
            should_visualize=True, render_type="mermaid",
            code="graph TD", title="图", reasoning="适合",
        )
        assert r.should_visualize is True
        assert r.render_type == "mermaid"
        assert r.code == "graph TD"
        assert r.title == "图"
        assert r.reasoning == "适合"
