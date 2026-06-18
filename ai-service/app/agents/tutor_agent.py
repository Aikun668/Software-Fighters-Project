import logging
from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.services.analogy_library import get_analogy_library
from app.services.domain_router import get_domain_router
from app.services.hallucination_guard import HallucinationGuard, kb_verify
from app.services.knowledge_base import get_kb
from app.services.llm_service import PROFILE_DIRECTOR, OpenAILLM
from app.utils.prompt_loader import build_prompt, interpolate_variables

logger = logging.getLogger(__name__)

MAX_MESSAGES = 20         # 传给 LLM 的最大消息数
HEAD_KEEP = 4             # 超限时保留的开头消息数（上下文锚点）
RAG_QUERY_TURNS = 3       # RAG 检索时合并最近 N 条用户消息
RAG_QUERY_MAX_CHARS = 300  # RAG query 最大字符数

REPLY_STRATEGY_PROMPTS = {
    "direct_answer": "直接完整回答学生的问题，不需要反问澄清。",
    "answer_with_accommodation": (
        "直接给出完整方案或回答，方案中要针对学生提到的障碍做调整。"
        "例如学生说数学差，就在方案里包含数学前置知识的补充建议。"
        "回答末尾可以自然追问 1 个关键澄清问题，但回答本身必须完整有用。"
    ),
    "clarify_first": (
        "先共情一句，再问 1 个关键问题来澄清学生的具体情况。"
        "不要泛泛说「能再说说吗」，要针对性地问。问完后根据回答给方案。"
    ),
}


class TutorState(TypedDict, total=False):
    messages: list[dict]
    user_id: int
    student_profile: dict
    knowledge_context: str
    kb_top_score: float | None
    course_id: str
    domain: str
    response: str
    conversation_id: int | None  # 用于加载对话摘要
    conversation_summary: str
    style: str                   # "standard" | "socratic"
    socratic_round: int          # 苏格拉底追问轮次（0-based）


@kb_verify(fields=["response"])
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
        self._clarity_llm = None

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
    def _extract_text(content: str | list | None) -> str:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                if isinstance(text, str):
                    parts.append(text)
        return " ".join(parts)

    @staticmethod
    def _build_rag_query(messages: list[dict]) -> str:
        """构建多轮 RAG 检索 query。

        合并最近 RAG_QUERY_TURNS 条用户消息，解决「第1个问题里提到的卷积」
        这类跨轮指代无法被单条消息捕获的问题。
        """
        user_msgs = [
            TutorAgent._extract_text(m.get("content", ""))
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

    def _get_clarity_llm(self):
        if self._clarity_llm is None:
            cfg = PROFILE_DIRECTOR.default
            self._clarity_llm = OpenAILLM(
                temperature=cfg.temperature,
                max_tokens=128,
                use_mock=self.use_mock_llm,
                model=cfg.model,
                api_key=cfg.api_key,
                base_url=cfg.base_url,
            )
        return self._clarity_llm

    async def _classify_clarity(self, message: str) -> dict:
        """调用 flash LLM 判断学生意图清晰度。失败时返回安全默认值。"""
        system_prompt = build_prompt(
            self.agent_name, filename="clarity_check.yaml", key="system"
        )
        user_template = build_prompt(
            self.agent_name, filename="clarity_check.yaml", key="user"
        )
        user_prompt = interpolate_variables(user_template, {"message": message})
        try:
            return await self._call_llm_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                expected_key="has_clear_goal",
                fallback={"has_clear_goal": False, "has_blocker": False, "needs_clarification": True},
                max_retries=1,
                llm=self._get_clarity_llm(),
            )
        except Exception:
            return {"has_clear_goal": False, "has_blocker": False, "needs_clarification": True}

    @staticmethod
    def _pick_reply_strategy(clarity: dict) -> str:
        if clarity["needs_clarification"] and not clarity["has_clear_goal"]:
            return "clarify_first"
        if clarity["has_clear_goal"] and clarity["has_blocker"]:
            return "answer_with_accommodation"
        if clarity["has_clear_goal"]:
            return "direct_answer"
        return "clarify_first"

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
        kb_top_score: float | None = None
        try:
            kb = get_kb()
            if not kb.is_empty():
                docs = kb.search(query, top_k=3)
                if docs:
                    kb_top_score = docs[0].get("score")
                    # format_context 重新 search 一次，但结果一致（幂等）
                    # 直接用 docs 构建 context 避免重复查询
                    parts = ["【参考知识库内容】"]
                    for i, doc in enumerate(docs, 1):
                        parts.append(f"[{i}] {doc['content']}")
                    knowledge_context = "\n".join(parts)
        except Exception as e:
            logger.warning(f"Knowledge retrieval failed: {e}")

        return {
            "knowledge_context": knowledge_context,
            "kb_top_score": kb_top_score,
        }

    async def _respond_node(self, state: TutorState) -> dict:
        """基于画像和 RAG 上下文生成回复。style="socratic" 时动态加载苏格拉底 prompt。

        领域路由 + KB 门控 + 类比门控 + 动态 system prompt 三层防护。"""
        messages = state.get("messages", [])
        student_profile = state.get("student_profile", {})
        knowledge_context = state.get("knowledge_context", "")
        kb_top_score = state.get("kb_top_score")
        course_id = state.get("course_id", "")
        style = state.get("style", "standard")
        socratic_round = state.get("socratic_round", 0)

        truncated = self._truncate_messages(messages)
        profile_text = self._format_profile(student_profile)

        # ── Layer 1+2: 领域路由 + KB 门控 ──
        query = self._build_rag_query(messages)
        router = get_domain_router()
        domain = router.classify(query, course_id=course_id, kb_top_score=kb_top_score)

        # 非 AI 领域 / KB 不相关：清空 KB 上下文，LLM 用自身知识回答
        if domain == "general" or not router.should_inject_kb(kb_top_score):
            knowledge_context = ""

        # ── 动态 domain_context（Layer 3: 动态 system prompt） ──
        domain_context = (
            "，当前课程为《人工智能导论》。优先使用知识库内容回答。"
            if domain == "ai" else
            "。用通用知识回答学生问题，涵盖各类学科，不受特定课程限制。"
        )

        # ── 意图清晰度分类（替代 system.yaml 语境感知软规则）──
        clarity = await self._classify_clarity(query)
        strategy = self._pick_reply_strategy(clarity)
        strategy_prompt = REPLY_STRATEGY_PROMPTS[strategy]

        if style == "socratic":
            if socratic_round >= 3:
                socratic_instruction = (
                    f"⚠️ 当前为第 {socratic_round} 轮（最后一轮），已经不是引导轮次，"
                    "请直接给出完整、清晰的解答，并简要标注学生之前卡在哪个环节。"
                )
            else:
                socratic_instruction = (
                    f"当前为第 {socratic_round} 轮引导。"
                    "请你提出引导性的问题，不要给出完整答案。"
                )
            socratic_prompt = self._load_extra_prompt("socratic.yaml", key="system")
            system_with_context = interpolate_variables(
                socratic_prompt,
                {
                    "student_profile": profile_text,
                    "knowledge_context": knowledge_context,
                    "socratic_instruction": socratic_instruction,
                    "domain_context": domain_context,
                    "reply_strategy": strategy_prompt,
                },
            )
        else:
            system_with_context = interpolate_variables(
                self.system_prompt,
                {
                    "student_profile": profile_text,
                    "knowledge_context": knowledge_context,
                    "domain_context": domain_context,
                    "reply_strategy": strategy_prompt,
                },
            )

            # Inject follow-up instruction for beginner students
            followup_context = self._load_followup_context(student_profile)
            if followup_context:
                system_with_context += "\n\n" + followup_context

            # ── 类比门控：只在 AI 领域注入类比 ──
            if router.should_inject_analogy(domain):
                try:
                    analogy_text = get_analogy_library().format_for_prompt(
                        query, domain=domain
                    )
                    if analogy_text:
                        system_with_context += "\n\n" + analogy_text
                except Exception:
                    pass

        # Inject conversation summary (LLM-compressed history)
        conversation_summary = state.get("conversation_summary", "")
        if conversation_summary:
            truncated_summary = conversation_summary[:1200]
            system_with_context += (
                "\n\n## 对话历史摘要（经过压缩的早期对话记录）\n"
                + truncated_summary
                + "\n---"
            )

        try:
            response = ""
            async for chunk in self.llm.chat_stream(
                truncated, system_prompt=system_with_context
            ):
                response += chunk
        except (ConnectionError, RuntimeError, ValueError) as e:
            logger.error(f"Tutor respond failed: {e}")
            response = "抱歉，我暂时无法回答这个问题。请稍后再试。"

        # ── 幻觉守护只对 AI 领域生效 ──
        if domain == "ai":
            try:
                kb = get_kb()
                guard = HallucinationGuard(kb)
                verified = guard.verify_and_format(response)
                if verified != response:
                    response = verified
            except Exception as e:
                logger.warning(f"Hallucination guard check failed: {e}")

        return {"response": response, "domain": domain}
