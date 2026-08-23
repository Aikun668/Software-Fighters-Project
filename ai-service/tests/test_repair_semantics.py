"""一次 Repair 语义测试：repair context 进入 LLM prompt + pre/post artifact。"""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.agents.content_agent import ContentAgent
from app.agents.interactive_diagram_agent import InteractiveDiagramAgent
from app.services.diagram_schema import build_fallback_diagram
from app.services.resource_quality_gate import ValidationResult, ReviewDecision
from app.workflows.resource_gen import ResourceGenWorkflow


@pytest.mark.asyncio
async def test_content_agent_repair_context_enters_prompt():
    agent = ContentAgent(use_mock_llm=True)
    captured = []

    async def fake_chat(messages, system_prompt=""):
        for m in messages:
            if m.get("role") == "user":
                captured.append(m["content"])
        return '{"sections": [{"heading": "概述", "focus": "内容"}]}'

    agent.llm.chat = fake_chat

    state = {
        "topic": "反向传播",
        "outline": {"sections": [{"heading": "概述", "focus": "概念"}]},
        "sub_type": "overview",
        "student_profile": {},
        "repair_instructions": ["补充数值示例", "修正公式符号"],
        "previous_blocks": [{"type": "section", "heading": "概述", "content": "旧草稿内容"}],
    }
    result = await agent._generate_node(state)
    assert result.get("blocks")
    assert captured
    prompt = captured[0]
    assert "补充数值示例" in prompt
    assert "修正公式符号" in prompt
    assert "旧草稿内容" in prompt, "原草稿应进入 repair prompt"


@pytest.mark.asyncio
async def test_diagram_agent_repair_context_enters_prompt():
    agent = InteractiveDiagramAgent(use_mock_llm=True)
    captured = []
    prev = build_fallback_diagram("CNN", "architecture")

    async def fake_chat(messages, system_prompt=""):
        for m in messages:
            if m.get("role") == "user":
                captured.append(m["content"])
        return json.dumps({"diagram": prev})

    agent.llm.chat = fake_chat

    state = {
        "topic": "CNN 架构",
        "diagram_type": "architecture",
        "student_profile": {},
        "repair_instructions": ["补充池化层", "修正边关系"],
        "previous_blocks": [{"type": "interactive_diagram", "diagram": prev}],
    }
    result = await agent._generate_node(state)
    assert result.get("blocks")
    assert captured
    prompt = captured[0]
    assert "补充池化层" in prompt
    assert "修正边关系" in prompt
    assert "CNN 图解" in prompt, "原图解应进入 repair prompt"


def _build_repair_workflow():
    wf = ResourceGenWorkflow(use_mock=True, quality_mode="active")
    wf.validator.validate = lambda rt, blocks: ValidationResult(True, "")

    async def fake_review(topic, resource_type, content_blocks, student_profile):
        return ReviewDecision("repair", "需要补充示例", ["补充示例"])

    wf.reviewer.review = fake_review
    calls = {"count": 0}

    async def fake_run(state):
        calls["count"] += 1
        if state.get("repair_instructions"):
            return {
                "blocks": [{"type": "section", "heading": "新", "content": "修订后内容"}],
                "response": "ok",
                "questions": [],
            }
        return {
            "blocks": [{"type": "section", "heading": "旧", "content": "修订前内容"}],
            "response": "ok",
            "questions": [],
        }

    async def fake_plan_outline(topic, student_profile):
        return {"outline": {}}

    wf.content_agent.plan_outline = fake_plan_outline
    wf.content_agent.run = fake_run
    for name in wf._agent_map:
        wf._agent_map[name].run = fake_run
    return wf, calls


@pytest.mark.asyncio
async def test_repair_preserves_pre_repair_blocks_and_runs_once():
    wf, calls = _build_repair_workflow()
    result = await wf.run({
        "topic": "反向传播",
        "resource_type": "document",
        "student_profile": {},
        "user_id": 1,
    })
    assert result["repair_attempted"] is True
    assert result["pre_repair_blocks"][0]["heading"] == "旧"
    assert result["content_blocks"][0]["heading"] == "新"
    assert calls["count"] == 2, "generate + repair 各一次，最多 repair 一次"


@pytest.mark.asyncio
async def test_content_agent_guide_repair_context_enters_prompt():
    agent = ContentAgent(use_mock_llm=True)
    captured = []

    async def fake_chat(messages, system_prompt=""):
        for m in messages:
            if m.get("role") == "user":
                captured.append(m["content"])
        return '{"steps": [{"heading": "步骤1", "code": "print(1)", "explanation": "说明"}]}'

    agent.llm.chat = fake_chat

    state = {
        "topic": "用Python实现排序",
        "outline": {"steps": [{"heading": "旧步骤", "code": "", "explanation": "旧说明"}]},
        "sub_type": "guide",
        "student_profile": {},
        "repair_instructions": ["补充边界处理", "添加注释"],
        "previous_blocks": [{"type": "code", "heading": "旧步骤", "content": "old code"}],
    }
    result = await agent._generate_node(state)
    assert result.get("blocks")
    assert captured
    prompt = captured[0]
    assert "补充边界处理" in prompt
    assert "添加注释" in prompt
    assert "旧步骤" in prompt and "old code" in prompt, "原草稿应进入 guide repair prompt"


@pytest.mark.asyncio
async def test_repair_exception_preserves_pre_repair_blocks():
    wf = ResourceGenWorkflow(use_mock=True, quality_mode="active")
    wf.validator.validate = lambda rt, blocks: ValidationResult(True, "")

    async def fake_review(topic, resource_type, content_blocks, student_profile):
        return ReviewDecision("repair", "需要补充示例", ["补充示例"])

    wf.reviewer.review = fake_review
    calls = {"count": 0}

    async def fake_run(state):
        calls["count"] += 1
        if state.get("repair_instructions"):
            raise RuntimeError("specialist repair failed")
        return {
            "blocks": [{"type": "section", "heading": "旧", "content": "原草稿内容"}],
            "response": "ok",
            "questions": [],
        }

    async def fake_plan_outline(topic, student_profile):
        return {"outline": {}}

    wf.content_agent.plan_outline = fake_plan_outline
    wf.content_agent.run = fake_run
    for name in wf._agent_map:
        wf._agent_map[name].run = fake_run

    result = await wf.run({
        "topic": "反向传播",
        "resource_type": "document",
        "student_profile": {},
        "user_id": 1,
    })
    assert result["repair_attempted"] is True
    assert result["pre_repair_blocks"][0]["heading"] == "旧"
    assert result["content_blocks"][0]["heading"] == "旧", "异常时保留原 draft 作为最终交付"


@pytest.mark.asyncio
async def test_runner_saves_pre_and_post_artifact(tmp_path):
    from scripts.run_resource_workflow_cases import run_one

    workflow = MagicMock()
    workflow.run = AsyncMock(return_value={
        "run_id": "r1",
        "agent_name": "content",
        "content_blocks": [{"type": "section", "heading": "新", "content": "修订后"}],
        "response": "已生成",
        "repair_attempted": True,
        "repair_instructions": ["补充示例"],
        "pre_repair_blocks": [{"type": "section", "heading": "旧", "content": "修订前"}],
    })
    record = await run_one(
        workflow,
        {"case_id": "case-1", "topic": "t", "resource_type": "document", "student_profile": {}},
        tmp_path,
    )
    assert record["repair_attempted"] is True
    assert record["repair_instructions"] == ["补充示例"]
    assert "pre-repair.json" in record["pre_repair_artifact_path"]
    assert "artifact.json" in record["artifact_path"]
    assert (tmp_path / "case-1.pre-repair.json").exists()
    assert (tmp_path / "case-1.artifact.json").exists()
