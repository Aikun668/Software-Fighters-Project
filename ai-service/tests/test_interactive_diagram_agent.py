"""InteractiveDiagramAgent 结构化输出测试。"""

import pytest

from app.agents.interactive_diagram_agent import InteractiveDiagramAgent


@pytest.mark.asyncio
async def test_agent_produces_structured_diagram_not_html():
    agent = InteractiveDiagramAgent(use_mock_llm=True)
    result = await agent.run(
        {"topic": "CNN 架构", "diagram_type": "architecture", "student_profile": {}}
    )
    blocks = result.get("blocks", [])
    assert blocks
    block = blocks[0]
    assert block["type"] == "interactive_diagram"
    diagram = block.get("diagram")
    assert isinstance(diagram, dict), "应产出结构化 diagram，而非 HTML"
    assert diagram.get("schema_version") == "v1"
    assert "<" not in str(block.get("content", "")), "content 不应含 HTML"
    assert "<" not in str(diagram), "diagram 不应含 HTML"


@pytest.mark.asyncio
async def test_agent_reports_diagram_source():
    agent = InteractiveDiagramAgent(use_mock_llm=True)
    result = await agent.run(
        {"topic": "CNN 架构", "diagram_type": "architecture", "student_profile": {}}
    )
    # 解析失败时应回退，diagram_source 标记为 fallback
    assert result.get("diagram_source") == "fallback"
    assert result.get("diagram_schema_version") == "v1"
