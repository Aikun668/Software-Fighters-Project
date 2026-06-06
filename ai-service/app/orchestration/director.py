"""Director — 动态 Agent 路由器

借鉴 OpenMAIC Director 3 路由策略:
  1. Rule fast-path:   关键词 regex 匹配 → 直接返回 agent 集合（80%+ 覆盖）
  2. Profile filter:   knowledge_base < 30 跳过 code, visual learner 必加 mindmap
  3. LLM fallback:     无关键词匹配时，一次 cheap LLM 调用决定 agent 集合

不调用 LLM 的常见场景零延迟。
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RouteDecision:
    selected_agents: list[str] = field(default_factory=list)
    rationale: str = ""
    strategy: str = ""  # "rule" | "llm"


class Director:
    TOPIC_AGENT_MAP: dict[str, list[str]] = {
        "python|编程|代码|语言基础|函数|类|模块": ["content", "code", "mindmap", "exercise", "flashcard"],
        "机器学习|深度学习|神经网络|AI|人工智能": ["content", "code", "exercise", "reading", "flashcard"],
        "数学|算法|线性代数|概率|统计|微积分": ["content", "code", "exercise", "flashcard"],
        "概念|理论|原理|体系|概述|导论": ["content", "reading", "mindmap", "flashcard"],
        "框架|工具|实战|项目|应用|部署|工程": ["content", "code", "exercise", "reading", "flashcard"],
        "数据|数据库|SQL|数据处理|分析|可视化": ["content", "code", "exercise", "flashcard"],
    }

    DEFAULT_AGENTS: list[str] = ["content", "exercise", "mindmap", "reading", "code", "flashcard"]
    CODE_KB_THRESHOLD: int = 30

    def __init__(self, use_mock: bool = False, model_profile=None):
        self.use_mock = use_mock
        self._model_profile = model_profile
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            from app.services.llm_service import create_llm

            if self._model_profile is not None:
                cfg = self._model_profile.default
                self._llm = create_llm(
                    model=cfg.model or None,
                    temperature=cfg.temperature,
                    max_tokens=cfg.max_tokens,
                    use_mock=self.use_mock,
                )
            else:
                self._llm = create_llm(use_mock=self.use_mock)
        return self._llm

    async def route(self, topic: str, student_profile: dict | None = None) -> RouteDecision:
        """主入口：根据 topic + student_profile 动态选择 Agent 集合"""
        if student_profile is None:
            student_profile = {}

        decision = self._rule_route(topic, student_profile)
        if decision is not None:
            return decision

        return await self._llm_route(topic, student_profile)

    def _rule_route(
        self, topic: str, student_profile: dict
    ) -> RouteDecision | None:
        """关键词 fast-path 路由"""
        topic_lower = topic.lower()

        for pattern, agents in self.TOPIC_AGENT_MAP.items():
            if re.search(pattern, topic_lower):
                selected = self._apply_profile_filter(list(agents), student_profile)
                return RouteDecision(
                    selected_agents=selected,
                    rationale=f"关键词匹配: 主题 '{topic}' 命中模式 '{pattern}'",
                    strategy="rule",
                )

        return None

    def _apply_profile_filter(
        self, agents: list[str], profile: dict
    ) -> list[str]:
        """根据学生画像微调 agent 集合"""
        selected = list(agents)

        kb = profile.get("knowledge_base")
        if isinstance(kb, (int, float)) and kb < self.CODE_KB_THRESHOLD and "code" in selected:
            selected.remove("code")

        interest = profile.get("interest_direction")
        if isinstance(interest, str) and "visual" in interest.lower():
            if "mindmap" not in selected:
                selected.append("mindmap")
        elif isinstance(interest, list):
            interest_str = " ".join(str(v) for v in interest).lower()
            if "visual" in interest_str and "mindmap" not in selected:
                selected.append("mindmap")

        return selected

    def _default_route(self, topic: str) -> RouteDecision:
        """兜底路由（LLM 调用失败时使用）"""
        rationale = f"主题 '{topic}' 路由失败，使用默认全 Agent 集合"
        logger.debug(rationale)
        return RouteDecision(
            selected_agents=list(self.DEFAULT_AGENTS),
            rationale=rationale,
            strategy="llm",
        )

    async def _llm_route(
        self, topic: str, student_profile: dict
    ) -> RouteDecision:
        """LLM 驱动的路由决策（temperature=0, max_tokens=200）"""
        llm = self._get_llm()

        system_prompt = (
            "你是一个教育资源路由决策器。根据学生想学的主题和画像，"
            "决定需要生成哪些类型的资源。"
        )
        user_prompt = (
            f"学生想学: {topic}\n"
            f"学生画像: {self._format_profile(student_profile)}\n\n"
            f"可用的资源类型（agent）:\n"
            f"- content: 课程核心讲解内容（必须）\n"
            f"- exercise: 配套练习题\n"
            f"- mindmap: 思维导图/概念关系图\n"
            f"- reading: 拓展阅读推荐\n"
            f"- code: 代码实操案例\n"
            f"- flashcard: 记忆闪卡（核心概念问答）\n\n"
            f"请输出 JSON: {{\"agents\": [\"content\", ...], \"rationale\": \"...\"}}\n"
            f"直接输出 JSON，不要包含其他内容。"
        )

        try:
            messages = [{"role": "user", "content": user_prompt}]
            raw = await llm.chat(messages, system_prompt=system_prompt)

            from app.utils.json_parser import parse_llm_json

            result = parse_llm_json(raw, fallback={})
            agents = result.get("agents", self.DEFAULT_AGENTS)
            if not isinstance(agents, list):
                agents = list(self.DEFAULT_AGENTS)
            agents = [a for a in agents if a in self.DEFAULT_AGENTS]
            if not agents:
                agents = list(self.DEFAULT_AGENTS)

            return RouteDecision(
                selected_agents=agents,
                rationale=result.get("rationale", "LLM 路由决策"),
                strategy="llm",
            )
        except Exception as e:
            logger.warning(f"LLM routing failed: {e}, using default agents")
            return self._default_route(topic)

    @staticmethod
    def _format_profile(profile: dict) -> str:
        if not profile:
            return "暂无画像"
        parts = []
        kb = profile.get("knowledge_base")
        if isinstance(kb, (int, float)):
            parts.append(f"知识基础: {kb}/100")
        goal = profile.get("learning_goal")
        if goal:
            parts.append(f"学习目标: {goal}")
        interest = profile.get("interest_direction")
        if interest:
            val = interest if isinstance(interest, str) else ", ".join(str(v) for v in interest)
            parts.append(f"兴趣方向: {val}")
        weak = profile.get("weak_points")
        if weak:
            val = weak if isinstance(weak, str) else ", ".join(str(v) for v in weak)
            parts.append(f"薄弱环节: {val}")
        return "; ".join(parts) if parts else "暂无画像"
