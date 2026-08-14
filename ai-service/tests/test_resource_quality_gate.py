"""资源质量门控 — Validator 契约测试。

覆盖 content 与 interactive_diagram 两类资源的确定性结构校验。
Validator 不调用 LLM，结果可复现。
"""

from app.services.resource_quality_gate import ResourceValidator


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


def test_diagram_validator_accepts_renderable_block():
    blocks = [{"type": "interactive_diagram", "heading": "CNN", "content": "<svg></svg>"}]
    result = ResourceValidator().validate("interactive_diagram", blocks)
    assert result.passed is True
