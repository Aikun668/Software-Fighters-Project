"""AgentTurnSummary — Agent 间对话的摘要数据结构

借鉴 OpenMAIC AgentTurnSummary: 每个 Agent 完成生成后发布结构化摘要，
下游 Agent 通过 build_peer_context_section() 获取 anti-repetition 提示块。
"""

from dataclasses import dataclass, field


@dataclass
class AgentTurnSummary:
    agent_name: str
    topic: str
    covered_concepts: list[str] = field(default_factory=list)
    generation_intent: str = ""
    avoid_duplicating: list[str] = field(default_factory=list)
    output_metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "topic": self.topic,
            "covered_concepts": self.covered_concepts,
            "generation_intent": self.generation_intent,
            "avoid_duplicating": self.avoid_duplicating,
            "output_metrics": self.output_metrics,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AgentTurnSummary":
        return cls(
            agent_name=d.get("agent_name", ""),
            topic=d.get("topic", ""),
            covered_concepts=d.get("covered_concepts", []),
            generation_intent=d.get("generation_intent", ""),
            avoid_duplicating=d.get("avoid_duplicating", []),
            output_metrics=d.get("output_metrics", {}),
        )

    @staticmethod
    def build_peer_context_section(
        for_agent: str,
        summaries: list["AgentTurnSummary"],
        max_items: int = 5,
    ) -> str:
        """构建 anti-repetition 提示块，供下游 Agent prompt 注入。

        排除 for_agent 自身的摘要，按 output_metrics.word_count 降序排列。
        """
        peers = [s for s in summaries if s.agent_name != for_agent]
        if not peers:
            return ""

        lines = ["\n[其它Agent已生成的内容 —— 请勿重复]"]
        for i, s in enumerate(peers[:max_items], 1):
            concepts = ", ".join(s.covered_concepts[:4]) or "(无)"
            intent = s.generation_intent or "(未指定)"
            avoid = ", ".join(s.avoid_duplicating[:2]) or "(无)"
            lines.append(
                f"{i}. [{s.agent_name}] 已覆盖概念: {concepts}\n"
                f"   生成意图: {intent}\n"
                f"   请避免重复: {avoid}"
            )
        lines.append("请在避免上述重复的前提下，从补充角度生成内容。")
        return "\n".join(lines)
