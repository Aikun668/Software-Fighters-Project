"""Pydantic data models for visualize pipeline.

Reference: deeptutor/agents/visualize/models.py
"""

from typing import Literal

from pydantic import BaseModel, Field


class VisualizationAnalysis(BaseModel):
    """Output of the analysis stage."""

    render_type: Literal[
        "svg",
        "chartjs",
        "mermaid",
        "html",
    ] = Field(
        default="mermaid",
        description="渲染类型: svg(自定义矢量图), chartjs(数据图表), mermaid(结构化图), html(交互页面)",
    )
    description: str = Field(
        default="",
        description="可视化应展示的内容的高层描述",
    )
    data_description: str = Field(
        default="",
        description="要可视化的数据或元素的描述",
    )
    chart_type: str = Field(
        default="",
        description=(
            "chartjs: bar/line/pie/doughnut/radar/scatter/bubble/polarArea; "
            "mermaid: flowchart/sequenceDiagram/classDiagram/stateDiagram/erDiagram/gantt/mindmap; "
            "html: interactive/animation/walkthrough/quiz"
        ),
    )
    visual_elements: list[str] = Field(
        default_factory=list,
        description="需要包含的关键视觉元素或交互模块",
    )
    rationale: str = Field(
        default="",
        description="为什么选择这种 render_type",
    )


class CodeResult(BaseModel):
    """Output of the code generation stage."""

    code: str = Field(
        default="",
        description="完整的可视化代码",
    )
    title: str = Field(
        default="",
        description="图表标题",
    )
    notes: str = Field(
        default="",
        description="设计说明",
    )


class ReviewResult(BaseModel):
    """Output of the review / optimization stage."""

    optimized_code: str = Field(
        default="",
        description="最终代码（如果无需更改则与输入相同）",
    )
    changed: bool = Field(
        default=False,
        description="审查员是否做了修改",
    )
    review_notes: str = Field(
        default="",
        description="检查或修改的内容",
    )


class VisualizeOutput(BaseModel):
    """Final output of the visualize pipeline."""

    should_visualize: bool = Field(default=False)
    render_type: Literal["svg", "chartjs", "mermaid", "html", ""] = Field(default="")
    code: str = Field(default="")
    title: str = Field(default="")
    reasoning: str = Field(default="")