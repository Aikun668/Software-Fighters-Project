import asyncio
import logging
from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.services.knowledge_base import get_kb
from app.utils.content_guard import KBCoverageChecker
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)


class TutorState(TypedDict, total=False):
    messages: list[dict]
    user_id: int
    student_profile: dict
    knowledge_context: str
    response: str


class TutorAgent(BaseAgent):
    """智能答疑 Agent —— 基于 RAG 上下文回答学生问题"""

    def __init__(self, config=None, use_mock_llm: bool = True):
        super().__init__(
            agent_name="tutor_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
        )
        self.use_mock_llm = use_mock_llm

    def build_graph(self) -> "CompiledStateGraph":
        graph = StateGraph(TutorState)
        graph.add_node("retrieve", self._retrieve_node)
        graph.add_node("respond", self._respond_node)
        graph.set_entry_point("retrieve")
        graph.add_edge("retrieve", "respond")
        graph.set_finish_point("respond")
        return graph.compile()

    async def _retrieve_node(self, state: TutorState) -> dict:
        messages = state.get("messages", [])
        last_msg = messages[-1] if messages else {}
        query = (last_msg.get("content", "") if isinstance(last_msg, dict) else "")[:100]
        
        knowledge_context = ""
        try:
            kb = get_kb()
            if not kb.is_empty():
                knowledge_context = kb.format_context(query, top_k=3)
        except Exception as e:
            logger.warning(f"Knowledge retrieval failed: {e}")
        
        return {"knowledge_context": knowledge_context}

    async def _respond_node(self, state: TutorState) -> dict:
        """基于画像和上下文生成回复"""
        messages = state.get("messages", [])
        student_profile = state.get("student_profile", {})
        knowledge_context = state.get("knowledge_context", "")

        profile_text = self._format_profile(student_profile)
        system_with_context = interpolate_variables(
            self.system_prompt,
            {
                "student_profile": profile_text,
                "knowledge_context": knowledge_context,
            },
        )

        try:
            response = ""
            async for chunk in self.llm.chat_stream(
                messages, system_prompt=system_with_context
            ):
                response += chunk
        except (ConnectionError, RuntimeError, ValueError) as e:
            logger.error(f"Tutor respond failed: {e}")
            response = "抱歉，我暂时无法回答这个问题。请稍后再试。"
        except Exception as e:
            logger.error(f"Tutor respond unexpected error: {e}", exc_info=True)
            response = "抱歉，我暂时无法回答这个问题。请稍后再试。"

        try:
            results = KBCoverageChecker.check_coverage(response, get_kb())
            if results:
                weak = [r for r in results if r.coverage == "WEAK"]
                logger.info(
                    f"KBCoverage: {len(weak)}/{len(results)} claims WEAK coverage"
                )
                if weak:
                    weak.sort(key=lambda r: len(r.claim), reverse=True)
                    for w in weak:
                        idx = response.find(w.claim)
                        if idx >= 0:
                            response = response[:idx + len(w.claim)] + "[需要验证]" + response[idx + len(w.claim):]
        except Exception as e:
            logger.warning(f"KBCoverage check failed: {e}")

        return {"response": response}

