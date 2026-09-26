import pytest


class TestReflectionAgent:
    @pytest.mark.asyncio
    async def test_fallback_without_llm(self):
        from app.agents.reflection_agent import ReflectionAgent

        agent = ReflectionAgent(use_mock_llm=True)
        state = await agent.run({"topic": "梯度下降", "student_profile": {}})

        assert len(state["reflection_questions"]) > 0
        assert isinstance(state["action_plan"], dict)

    @pytest.mark.asyncio
    async def test_with_session_summary(self):
        from app.agents.reflection_agent import ReflectionAgent

        agent = ReflectionAgent(use_mock_llm=True)
        state = await agent.run({
            "topic": "神经网络",
            "session_summary": "学生对反向传播理解模糊，但能正确描述前向传播",
            "student_profile": {"knowledge_base": 50},
        })

        assert "reflection_questions" in state
        assert "knowledge_gaps" in state


class TestProjectAgent:
    @pytest.mark.asyncio
    async def test_fallback_project(self):
        from app.agents.project_agent import ProjectAgent

        agent = ProjectAgent(use_mock_llm=True)
        state = await agent.run({"topic": "Python基础", "student_profile": {}})

        assert state["project_title"]
        assert len(state["milestones"]) >= 2
        assert len(state["learning_objectives"]) > 0

    @pytest.mark.asyncio
    async def test_with_prerequisites(self):
        from app.agents.project_agent import ProjectAgent

        agent = ProjectAgent(use_mock_llm=True)
        state = await agent.run({
            "topic": "Flask Web开发",
            "prerequisites": "Python基础, HTML, HTTP协议",
            "student_profile": {"knowledge_base": 60},
        })

        assert "tech_stack" in state
        assert state["difficulty"] in ("beginner", "intermediate", "advanced")


class TestExerciseVariantAgent:
    @pytest.mark.asyncio
    async def test_fallback_variants(self):
        from app.agents.exercise_variant_agent import ExerciseVariantAgent

        agent = ExerciseVariantAgent(use_mock_llm=True)
        state = await agent.run({
            "original_question": {
                "question": "什么是梯度下降？",
                "question_type": "short_answer",
                "correct_answer": "一种优化算法",
            },
            "count": 3,
            "student_profile": {},
        })

        assert len(state["variants"]) == 3
        assert state["variant_strategy"]

    @pytest.mark.asyncio
    async def test_custom_count(self):
        from app.agents.exercise_variant_agent import ExerciseVariantAgent

        agent = ExerciseVariantAgent(use_mock_llm=True)
        state = await agent.run({
            "original_question": {"question": "Python中list和tuple的区别"},
            "count": 5,
            "strategy": "change_context",
        })

        assert len(state["variants"]) > 0


class TestDeepSolveWorkflow:
    @pytest.mark.asyncio
    async def test_all_four_stages_run(self):
        from app.workflows.deep_solve import DeepSolveWorkflow

        workflow = DeepSolveWorkflow()
        state = await workflow.run({
            "question": "已知 f(x)=x^2, 求 f'(3)",
            "context": "微积分基础知识",
            "student_profile": {"knowledge_base": 60},
        })

        assert "plan" in state
        assert "investigation" in state
        assert "solution" in state
        assert "verification" in state
        assert state["plan"].get("steps")

    @pytest.mark.asyncio
    async def test_empty_question_handled(self):
        from app.workflows.deep_solve import DeepSolveWorkflow

        workflow = DeepSolveWorkflow()
        state = await workflow.run({
            "question": "",
            "context": "",
            "student_profile": {},
        })

        assert "response" in state
        assert state.get("plan") is not None

    @pytest.mark.asyncio
    async def test_ds_a01_is_base_workflow_and_emits_node_events(self, monkeypatch):
        """接入 `BaseWorkflow`（P1 修复，契约 `DS-A01`）。

        此前 `DeepSolveWorkflow` 是四个工作流中唯一不继承基类的实现，拿不到
        节点事件 / 上游事件源复用 / 回退开关。本用例锁住「接入基类且四个阶段
        节点事件可达」。
        """
        monkeypatch.delenv("AI_SERVICE_GRAPH_STREAM", raising=False)

        from app.events.stream import ProgressEventType, StreamEmitter
        from app.workflows.base_workflow import BaseWorkflow
        from app.workflows.deep_solve import DeepSolveWorkflow

        assert issubclass(DeepSolveWorkflow, BaseWorkflow), (
            "DeepSolveWorkflow 必须继承 BaseWorkflow（P3-E 节点事件与回退开关的前提）"
        )

        captured: list[StreamEmitter] = []
        real_init = StreamEmitter.__init__

        def _spy_init(self, *args, **kwargs):
            real_init(self, *args, **kwargs)
            captured.append(self)

        monkeypatch.setattr(StreamEmitter, "__init__", _spy_init)

        workflow = DeepSolveWorkflow(use_mock=True)
        await workflow.run({"question": "1+1=?", "context": "", "student_profile": {}})

        assert captured, "未创建事件源"
        nodes = [
            event.data["node"] for event in captured[0].events
            if event.type is ProgressEventType.NODE_COMPLETED
        ]
        assert {"plan", "investigate", "solve", "verify"} <= set(nodes), nodes


class TestPDFExporter:
    def test_export_basic_content(self):
        from app.utils.pdf_exporter import export_to_pdf
        import tempfile, os

        content_blocks = [
            {"type": "section", "heading": "Overview", "content": "## Test\nThis is test content."},
            {"type": "code", "heading": "Example Code", "content": "```python\nprint('hello')\n```"},
            {"type": "callout", "heading": "Note", "content": "Important tip"},
        ]

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name

        try:
            result = export_to_pdf(content_blocks, path, title="Test PDF")
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_export_empty_blocks(self):
        from app.utils.pdf_exporter import export_to_pdf
        import tempfile, os

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name

        try:
            result = export_to_pdf([], path, title="Empty Doc")
            assert os.path.exists(result)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_export_with_mindmap(self):
        from app.utils.pdf_exporter import export_to_pdf
        import tempfile, os, json

        content_blocks = [{
            "type": "mindmap",
            "heading": "Knowledge Graph",
            "content": json.dumps({"nodes": [{"name": "A"}, {"name": "B"}]}),
        }]

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name

        try:
            result = export_to_pdf(content_blocks, path, title="Graph PDF")
            assert os.path.exists(result)
        finally:
            if os.path.exists(path):
                os.unlink(path)
