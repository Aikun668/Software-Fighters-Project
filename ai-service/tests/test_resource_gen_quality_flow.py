"""资源生成 Workflow 质量门控状态机测试。

覆盖质量门控接入 ResourceGenWorkflow 后的状态转换：
  - pass 不修复、repair 只修复一次、skipped 不阻断、shadow 只记录不干预。
"""

import pytest

from app.workflows.resource_gen import ResourceGenWorkflow
from app.services.resource_quality_gate import ValidationResult, ReviewDecision


def _valid_section_blocks():
    return [{"type": "section", "heading": "概念", "content": "用于计算梯度。"}]


def valid_content_state() -> dict:
    """构造一个会路由到 content agent 的合法输入状态。"""
    return {
        "topic": "反向传播",
        "resource_type": "document",
        "student_profile": {"knowledge_base": 50},
        "user_id": 1,
    }


def _make_fake_specialist(agent_name: str):
    """返回一个 fake agent，run() 产出可通过 Validator 的块。"""
    block_type = "section" if agent_name == "content" else agent_name
    async def fake_run(state):
        return {
            "blocks": [{"type": block_type, "heading": "概念", "content": "用于计算梯度。"}],
            "response": "已生成。",
            "questions": [],
        }
    return fake_run


def build_workflow_with_fake_services(review_status="pass", quality_mode="active"):
    """构造一个 validator / reviewer / specialist 全为 fake 的 workflow。"""
    wf = ResourceGenWorkflow(use_mock=True, quality_mode=quality_mode)

    # fake validator：永远通过
    wf.validator.validate = lambda resource_type, content_blocks: ValidationResult(True, "")

    # fake reviewer：返回给定 status
    async def fake_review(topic, resource_type, content_blocks, student_profile):
        return ReviewDecision(
            review_status,
            "测试原因",
            ["补充示例"] if review_status == "repair" else [],
        )
    wf.reviewer.review = fake_review

    # fake content_agent：plan_outline + run
    async def fake_plan_outline(topic, student_profile):
        return {"outline": {}}
    wf.content_agent.plan_outline = fake_plan_outline
    wf.content_agent.run = _make_fake_specialist("content")

    # fake 所有 specialist agent
    for name in wf._agent_map:
        wf._agent_map[name].run = _make_fake_specialist(name)

    return wf


@pytest.mark.asyncio
async def test_passed_review_finalizes_without_repair():
    workflow = build_workflow_with_fake_services(review_status="pass")
    result = await workflow.run(valid_content_state())
    assert result["review_status"] == "pass"
    assert result["repair_attempted"] is False
    assert result["final_status"] == "success"


@pytest.mark.asyncio
async def test_repair_runs_once_then_delivers_valid_output():
    workflow = build_workflow_with_fake_services(review_status="repair")
    result = await workflow.run(valid_content_state())
    assert result["repair_attempted"] is True
    assert result["final_status"] == "success"


@pytest.mark.asyncio
async def test_skipped_review_does_not_block_valid_output():
    workflow = build_workflow_with_fake_services(review_status="skipped")
    result = await workflow.run(valid_content_state())
    assert result["review_status"] == "skipped"
    assert result["content_blocks"]


@pytest.mark.asyncio
async def test_shadow_mode_records_repair_without_changing_output():
    workflow = build_workflow_with_fake_services(review_status="repair", quality_mode="shadow")
    result = await workflow.run(valid_content_state())
    assert result["review_status"] == "repair"
    assert result["repair_attempted"] is False
    assert result["final_status"] == "success"
