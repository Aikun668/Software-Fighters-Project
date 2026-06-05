import logging
from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.services.analogy_library import get_analogy_library
from app.services.hallucination_guard import HallucinationGuard
from app.services.knowledge_base import get_kb
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)

MAX_MESSAGES = 20         # 传给 LLM 的最大消息数
HEAD_KEEP = 4             # 超限时保留的开头消息数（上下文锚点）
RAG_QUERY_TURNS = 3       # RAG 检索时合并最近 N 条用户消息
RAG_QUERY_MAX_CHARS = 300  # RAG query 最大字符数


class TutorState(TypedDict, total=False):
    messages: list[dict]
    user_id: int
    student_profile: dict
    knowledge_context: str
    response: str
    conversation_id: int | None  # 用于加载对话摘要


class TutorAgent(BaseAgent):
    """智能答疑 Agent —— 基于 RAG 上下文回答学生问题"""

    def __init__(self, config=None, use_mock_llm: bool = False):
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

    # ── message truncation ──────────────────────────────────────

    @staticmethod
    def _truncate_messages(messages: list[dict]) -> list[dict]:
        """截断消息历史，防止 token 爆炸。

        策略：
        - ≤ MAX_MESSAGES 条：原样返回
        - > MAX_MESSAGES 条：保留开头 HEAD_KEEP 条（早期上下文）
          + 末尾 (MAX_MESSAGES - HEAD_KEEP) 条（最近对话）
        """
        if len(messages) <= MAX_MESSAGES:
            return messages

        head = messages[:HEAD_KEEP]
        tail = messages[-(MAX_MESSAGES - HEAD_KEEP):]
        logger.info(
            f"Truncated messages: {len(messages)} → {len(head) + len(tail)} "
            f"(head={len(head)}, tail={len(tail)})"
        )
        return head + tail

    # ── RAG query construction ──────────────────────────────────

    @staticmethod
    def _extract_text(content) -> str:
        """从纯文本或多模态 content 中提取文本"""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(
                p.get("text", "") for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )
        return ""

    @staticmethod
    def _build_rag_query(messages: list[dict]) -> str:
        """构建多轮 RAG 检索 query。

        合并最近 RAG_QUERY_TURNS 条用户消息，解决「第1个问题里提到的卷积」
        这类跨轮指代无法被单条消息捕获的问题。
        """
        user_msgs = [
            TutorAgent._extract_text(m.get("content", ""))
            if isinstance(m, dict) else ""
            for m in messages
            if isinstance(m, dict) and m.get("role") == "user"
        ]
        recent = user_msgs[-RAG_QUERY_TURNS:]

        # 短对话直接用最后一条
        if len(recent) <= 1:
            return (recent[0] if recent else "")[:RAG_QUERY_MAX_CHARS]

        # 拼接最近 N 条，分隔符明确
        combined = " | ".join(recent)
        if len(combined) <= RAG_QUERY_MAX_CHARS:
            return combined

        # 超出上限：优先保留最后一条完整内容，其余截断
        last = recent[-1]
        budget = RAG_QUERY_MAX_CHARS - len(last) - 3
        if budget > 0:
            prefix = " | ".join(recent[:-1])[:budget]
            return f"{prefix} | {last}"
        return last[:RAG_QUERY_MAX_CHARS]

    def _load_followup_context(self, profile: dict) -> str:
        """加载追问引导 prompt，初学阶段追加到系统指令中"""
        try:
            level = profile.get("level") or profile.get("knowledge_base")
            if isinstance(level, (int, float)) and level < 3:
                return self._load_extra_prompt("followup.yaml", key="system")
        except Exception:
            pass
        return ""

    # ── nodes ───────────────────────────────────────────────────

    async def _retrieve_node(self, state: TutorState) -> dict:
        messages = state.get("messages", [])
        query = self._build_rag_query(messages)

        knowledge_context = ""
        try:
            kb = get_kb()
            if not kb.is_empty():
                knowledge_context = kb.format_context(query, top_k=3)
        except Exception as e:
            logger.warning(f"Knowledge retrieval failed: {e}")

        return {"knowledge_context": knowledge_context}

    async def _respond_node(self, state: TutorState) -> dict:
        """基于画像和 RAG 上下文生成回复"""
        messages = state.get("messages", [])
        student_profile = state.get("student_profile", {})
        knowledge_context = state.get("knowledge_context", "")

        # 截断后再传给 LLM
        truncated = self._truncate_messages(messages)

        profile_text = self._format_profile(student_profile)
        system_with_context = interpolate_variables(
            self.system_prompt,
            {
                "student_profile": profile_text,
                "knowledge_context": knowledge_context,
            },
        )

        # Inject follow-up instruction for beginner students
        followup_context = self._load_followup_context(student_profile)
        if followup_context:
            system_with_context += "\n\n" + followup_context

        # Inject analogy if available for the query topic
        query = self._build_rag_query(messages)
        try:
            analogy_text = get_analogy_library().format_for_prompt(query)
            if analogy_text:
                system_with_context += "\n\n" + analogy_text
        except Exception:
            pass

        # Inject conversation summary (LLM-compressed history)
        conversation_id = state.get("conversation_id")
        if conversation_id:
            try:
                from app.services.conversation_service import get_conversation_service
                summary = await get_conversation_service().get_summary(conversation_id)
                if summary:
                    system_with_context += (
                        "\n\n## 对话历史摘要（经过压缩的早期对话记录）\n"
                        + summary
                        + "\n---"
                    )
            except Exception:
                pass

        try:
            response = ""
            async for chunk in self.llm.chat_stream(
                truncated, system_prompt=system_with_context
            ):
                response += chunk
        except (ConnectionError, RuntimeError, ValueError) as e:
            logger.error(f"Tutor respond failed: {e}")
            response = "抱歉，我暂时无法回答这个问题。请稍后再试。"

        try:
            kb = get_kb()
            guard = HallucinationGuard(kb)
            verified = guard.verify_and_format(response)
            if verified != response:
                response = verified
        except Exception as e:
            logger.warning(f"Hallucination guard check failed: {e}")

        return {"response": response}
