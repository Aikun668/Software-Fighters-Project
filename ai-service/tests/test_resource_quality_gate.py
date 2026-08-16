"""资源质量门控 — Validator 与 Judge 契约测试。

覆盖 content 与 interactive_diagram 两类资源：
  - ResourceValidator：确定性结构校验，不调用 LLM。
  - ResourceReviewService：轻量 LLM-as-Judge，只输出 pass | repair | skipped。
"""

import pytest
from unittest.mock import AsyncMock

from app.services.resource_quality_gate import ResourceValidator, ResourceReviewService


# ── ResourceValidator（确定性，不调用 LLM）────────────────────────

def test_content_validator_rejects_empty_blocks():
    result = ResourceValidator().validate("content", [])
    assert result.passed is False
    assert result.issues == ["content_blocks 不能为空"]


def test_content_validator_accepts_section_with_heading_and_content():
    blocks = [{"type": "section", "heading": "反向传播", "content": "用于计算梯度。"}]
    result = ResourceValidator().validate("content", blocks)
    assert result.passed is True


def test_diagram_validator_rejects_wrong_block_type():
    blocks = [{"type": "section", "heading": "CNN", "content": "文本"}]
    result = ResourceValidator().validate("interactive_diagram", blocks)
    assert result.passed is False
    assert "interactive_diagram" in result.reason


def test_diagram_validator_accepts_valid_schema():
    from app.services.diagram_schema import build_fallback_diagram
    diagram = build_fallback_diagram("CNN", "architecture")
    blocks = [{"type": "interactive_diagram", "heading": "CNN", "content": "摘要", "diagram": diagram}]
    result = ResourceValidator().validate("interactive_diagram", blocks)
    assert result.passed is True


def test_diagram_validator_rejects_invalid_schema():
    blocks = [{"type": "interactive_diagram", "heading": "CNN", "content": "摘要", "diagram": {"schema_version": "v2"}}]
    result = ResourceValidator().validate("interactive_diagram", blocks)
    assert result.passed is False


# ── ResourceReviewService（轻量 Judge）─────────────────────────────

@pytest.mark.asyncio
async def test_review_service_normalizes_repair_and_limits_fixes():
    service = ResourceReviewService(use_mock=True)
    service._chat = AsyncMock(return_value='{"decision":"repair","reason":"缺少步骤","fixes":["补充目标", "补充示例", "补充总结", "忽略这条"]}')
    result = await service.review("反向传播", "content", [{"type": "section", "heading": "概念", "content": "..."}], {})
    assert result.status == "repair"
    assert result.fixes == ["补充目标", "补充示例", "补充总结"]


@pytest.mark.asyncio
async def test_review_service_returns_skipped_on_invalid_json():
    service = ResourceReviewService(use_mock=True)
    service._chat = AsyncMock(return_value="not json")
    result = await service.review("CNN", "interactive_diagram", [{"type": "interactive_diagram", "content": "<svg/>"}], {})
    assert result.status == "skipped"


@pytest.mark.asyncio
async def test_review_service_normalizes_unknown_decision_to_pass():
    service = ResourceReviewService(use_mock=True)
    service._chat = AsyncMock(return_value='{"decision":"unknown","reason":"ok","fixes":[]}')
    result = await service.review("CNN", "content", [{"type": "section", "heading": "概念", "content": "..."}], {})
    assert result.status == "pass"
