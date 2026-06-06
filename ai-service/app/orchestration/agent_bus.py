"""AgentBus — 内存中的 AgentTurnSummary 收集器

借鉴 DeepTutor StreamBus 事件收集模式：每次 generate 前清空，
每个 Agent 完成后 submit 摘要，为下游 Agent 提供 peer context。
"""

from app.orchestration.agent_turn_summary import AgentTurnSummary


class AgentBus:
    """In-memory summary collector for agent turn summaries.

    Designed for sequential access within a single workflow run. The _summaries
    list is not protected by locks — concurrent access from multiple coroutines
    is not supported.
    """

    def __init__(self):
        self._summaries: list[AgentTurnSummary] = []

    def submit(self, summary: AgentTurnSummary) -> None:
        self._summaries.append(summary)

    def get_peer_context(self, for_agent: str) -> str:
        return AgentTurnSummary.build_peer_context_section(
            for_agent, self._summaries
        )

    def get_all_summaries(self) -> list[AgentTurnSummary]:
        return list(self._summaries)

    def clear(self) -> None:
        self._summaries.clear()

    def __len__(self) -> int:
        return len(self._summaries)
