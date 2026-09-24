"""
ResourceWhiteboard — 共享上下文白板

借鉴 OpenMAIC WhiteboardLedger + buildVirtualWhiteboardContext 模式：
ContentAgent 先跑完 → 提取关键信息写入 whiteboard → 下游 Agent 读取后注入 prompt。

【命名澄清】本类是 `@dataclass` 数据容器，**不是 Workflow**（无 LangGraph 图）。
  原位于 `app/workflows/`（目录语义不符），**P3-B1 移入 `app/orchestration/`**
  —— 与本目录的 `AgentTurnSummary` 同域（两者互为桥接，见 `to_agent_turn_summary`）。
  注：当前仍**无生产代码引用**（仅 `tests/test_resource_whiteboard.py`）。
"""

from dataclasses import dataclass, field


@dataclass
class ResourceWhiteboard:
    """共享上下文白板 — ContentAgent 写入，下游 Agent 读取"""

    topic: str = ""
    key_concepts: list[str] = field(default_factory=list)
    section_summaries: list[str] = field(default_factory=list)
    outline_subsections: list[str] = field(default_factory=list)
    code_focus: str = ""

    def to_context_text(self) -> str:
        """渲染为 LLM 可读的上下文文本"""
        lines = []
        lines.append(f"主题: {self.topic}")

        if self.key_concepts:
            lines.append(f"核心概念: {', '.join(self.key_concepts)}")

        if self.section_summaries:
            lines.append("内容概述:")
            for s in self.section_summaries:
                lines.append(f"  - {s}")

        if self.outline_subsections:
            lines.append(f"大纲结构: {' → '.join(self.outline_subsections)}")

        if self.code_focus:
            lines.append(f"代码重点: {self.code_focus}")

        return "\n".join(lines)

    @classmethod
    def from_content_output(
        cls, topic: str, outline: dict, content_blocks: list[dict]
    ) -> "ResourceWhiteboard":
        """从 ContentAgent 产出中提取关键信息"""
        subsections = outline.get("subsections", [])
        outline_labels = [
            sub.get("heading", "") for sub in subsections if sub.get("heading")
        ]

        section_summaries = []
        for b in content_blocks:
            if b.get("type") == "section" and b.get("content"):
                text = str(b["content"])
                summary = text[:100].replace("\n", " ").strip()
                if summary:
                    section_summaries.append(
                        f"{b.get('heading', '')}: {summary}..."
                        if len(text) > 100
                        else f"{b.get('heading', '')}: {summary}"
                    )

        code_related = [
            s for s in subsections if s.get("role") in ("example", "application")
        ]
        code_focus = (
            code_related[0].get("focus", "") if code_related else topic
        )

        return cls(
            topic=topic,
            key_concepts=outline_labels[:8],
            section_summaries=section_summaries[:6],
            outline_subsections=outline_labels,
            code_focus=code_focus,
        )

    def to_agent_turn_summary(self) -> "AgentTurnSummary":
        """桥接：ResourceWhiteboard → AgentTurnSummary"""
        from app.orchestration.agent_turn_summary import AgentTurnSummary

        return AgentTurnSummary(
            agent_name="ContentAgent",
            topic=self.topic,
            covered_concepts=list(self.key_concepts),
            generation_intent=(
                f"讲解{self.topic}的核心概念"
                f"（{', '.join(self.key_concepts[:3])}等）"
                if self.key_concepts
                else f"讲解{self.topic}的核心概念"
            ),
            avoid_duplicating=list(self.key_concepts[:4]),
            output_metrics={
                "section_count": len(self.section_summaries),
                "concept_count": len(self.key_concepts),
            },
        )

    @classmethod
    def from_turn_summary(
        cls, summary: "AgentTurnSummary"
    ) -> "ResourceWhiteboard":
        """桥接：AgentTurnSummary → ResourceWhiteboard"""
        return cls(
            topic=summary.topic,
            key_concepts=list(summary.covered_concepts),
            code_focus=(
                summary.covered_concepts[0] if summary.covered_concepts else ""
            ),
        )
