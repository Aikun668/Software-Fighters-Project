"""Director — 意图分类器（单 Agent 路由）

资源工坊核心路由逻辑:
  1. resource_type 显式传入 → 直接映射到 Agent（零延迟）
  2. Rule fast-path: 关键词 regex 匹配 → 单 Agent（80%+ 覆盖）
  3. LLM fallback:     无匹配时一次 cheap LLM 调用决定 Agent

设计原则：按输出格式分类，不按内容分类。
用户说「生成 CNN 代码」→ 只出代码，不出全家桶。
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── resource_type → agent_name 直接映射（含 inquiry service 别名）──
TYPE_TO_AGENT: dict[str, str] = {
    # 正式名称
    "document": "content",
    "interactive_diagram": "interactive_diagram",
    "code": "code",
    "project": "project",
    "mindmap": "mindmap",
    "flashcard": "flashcard",
    # inquiry service 兼容别名
    "content": "content",
    "tutorial": "content",
    "exercise": "code",       # legacy: exercise 类型走 code agent
    "reading": "content",     # legacy: reading → content 替代
    "video": "interactive_diagram",  # legacy: video → interactive_diagram
}

# ── 词根匹配：substring 代替 regex 穷举 ──
# 代码意图词根 — "写" 匹配 "写一个" "编写" "手写" 全部变体
CODE_ROOTS = [
    "写代码", "写个", "写一", "手写", "编程", "代码",
    "实现算法", "实现一个", "api", "demo", "示例",
]

# 报错诊断词根 — 覆盖书面语 + 口语
DIAG_ROOTS = [
    "报错", "错误", "出错", "bug", "debug", "调试", "异常",
    "排查", "挂了", "不work", "不行", "怎么办", "咋整",
    "修一下", "不收敛", "不下降", "没效果", "修了", "解决", "不对",
]

# ── 优先级分层路由表 ──
# Tier 1: 具体资源类型（先匹配，高优先级）
# Tier 2: 项目/实战（泛化动作词，中优先级）
# Tier 3: 课程文档（最泛化，兜底）
# 注：code agent 独立走 CODE_ROOTS 检测（排在 project 前 content 后）

ROUTING_TIERS: list[tuple[str, list[str]]] = [
    # Tier 1 — 具体资源类型（最高优先级）
    ("interactive_diagram", [
        "可视化", "动画", "交互式", "流程图", "架构图", "数据流",
        "动态图", "动图", "图解", "演示图", "交互", "示意",
    ]),
    ("mindmap", [
        "思维导图", "脑图", "知识图谱", "概念图", "知识结构",
        "关系图", "梳理", "归纳", "知识框架",
    ]),
    ("flashcard", [
        "闪卡", "记忆卡", "背诵", "速记", "考点", "单词卡",
        "速查", "背一下",
    ]),
    # Tier 3 — 项目/实战（泛化动作词）
    ("project", [
        "项目", "实战", "练手", "搭建", "构建", "从零",
        "完整应用", "小应用", "做一个", "做个", "开发一个",
        "开发个", "mini",
    ]),
    # Tier 4 — 技术文档（最泛化，兜底）
    ("content", [
        "基础", "入门", "教程", "是什么", "原理", "理论", "概念",
        "学习", "介绍", "概述", "导论", "了解", "解释", "什么",
        "对比", "比较", "区别", "差异", "优缺点", "怎么学",
        "学好", "理解", "认识", "怎么", "如何", "步骤", "攻略",
        "实战", "训练", "手把手", "跟着",
    ]),
]

# fallback
DEFAULT_AGENT = "content"

SUPPORTED_AGENTS = frozenset({"content", "interactive_diagram", "code", "project", "mindmap", "flashcard"})


@dataclass(frozen=True)
class RouteDecision:
    agent_name: str = DEFAULT_AGENT
    sub_type: str | None = None  # "comparison" | "diagnosis" | None
    rationale: str = ""
    strategy: str = ""  # "type_direct" | "rule" | "llm"


class Director:
    """意图路由器 — 将用户输入映射到单个 Agent。

    路由策略:
      1. type_direct: resource_type 显式传入
      2. rule: 优先级分层 + 词根匹配（~85% 覆盖）
      3. llm:  规则未命中时 LLM 兜底（口语/方言/模糊表达）
    """

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

    # ── 主入口 ──

    async def route(
        self,
        topic: str,
        resource_type: str | None = None,
        student_profile: dict | None = None,
    ) -> RouteDecision:
        """根据 topic + 可选的 resource_type 路由到单个 Agent。

        Args:
            topic: 用户输入的原始主题文本
            resource_type: 前端显式传入的资源类型（可选）
            student_profile: 学生画像（预留，当前未使用）

        Returns:
            RouteDecision with agent_name and optional sub_type
        """
        # 策略 1: resource_type 显式传入 → 直接映射
        if resource_type and resource_type in TYPE_TO_AGENT:
            agent = TYPE_TO_AGENT[resource_type]
            sub = self._detect_sub_type(topic, agent)
            return RouteDecision(
                agent_name=agent,
                sub_type=sub,
                rationale=f"前端传入 resource_type='{resource_type}' → {agent}",
                strategy="type_direct",
            )

        # 策略 2: 优先级分层 + 词根匹配
        decision = self._rule_route(topic)
        if decision is not None:
            return decision

        # 策略 3: LLM 兜底（口语/方言/规则覆盖不到的表达）
        return await self._llm_route(topic)

    # ── 规则路由（优先级分层 + 词根匹配）──

    def _rule_route(self, topic: str) -> RouteDecision | None:
        """优先级分层匹配：具体资源 → 代码意图 → 项目 → 课程文档。

        顺序即优先级。命中即返回，不继续检查。
        词根用 substring 匹配，覆盖 "写一个/编写/手写" 等全部变体。
        """
        msg = topic.lower()

        # ── Tier 1: 具体资源类型（最高优先级，先匹配）──
        for agent, keywords in ROUTING_TIERS:
            for kw in keywords:
                if kw in msg:
                    sub = self._detect_sub_type(topic, agent)
                    return RouteDecision(
                        agent_name=agent, sub_type=sub,
                        rationale=f"具体资源关键词 '{kw}' → {agent}",
                        strategy="rule",
                    )

        # ── Tier 2: 代码意图检测（词根匹配，排在 project 前 content 后）──
        if any(root in msg for root in CODE_ROOTS):
            sub = self._detect_sub_type(topic, "code")
            return RouteDecision(
                agent_name="code", sub_type=sub,
                rationale=f"代码词根命中 → code",
                strategy="rule",
            )

        return None

    # ── 子类型检测 ──

    _AGENT_SUB_TYPES: dict[str, frozenset[str]] = {
        "content": frozenset({"overview", "guide", "comparison"}),
        "code": frozenset({"diagnosis"}),
    }

    @classmethod
    def _detect_sub_type(cls, topic: str, agent_name: str | None = None) -> str | None:
        """检测子类型（词根匹配 + 兼容性过滤）。

        content agent:
          - overview: 是什么/原理/结构/对比/图解 等概念理解类
          - guide: 怎么/如何/实现/训练/构建/解决 等动手实操类
          - comparison: 保留向后兼容
        code agent:
          - diagnosis: 报错/调试/排查
        """
        detected = None
        msg = topic.lower()

        # ── guide 检测（优先，因为包含具体动作词）──
        guide_roots = ("怎么", "如何", "实现", "训练", "构建", "解决", "步骤",
                       "教程", "实战", "跟着", "做一个", "写一个", "开发一个",
                       "攻略", "动手", "手把手", "一步步", "搭建")
        if any(kw in msg for kw in guide_roots):
            detected = "guide"

        # ── comparison 检测 ──
        if not detected and any(kw in msg for kw in ("对比", "比较", "区别", "差异",
                "vs", "优缺点", "哪个好", "选哪个")):
            detected = "comparison"

        # ── overview 检测（兜底：概念理解类词）──
        if not detected and any(kw in msg for kw in ("是什么", "原理", "结构",
                "概念", "图解", "架构", "理解", "认识", "了解", "介绍", "概述",
                "导论", "解释", "什么", "怎么学", "学好", "基础", "入门", "理论",
                "流程", "机制", "核心", "组成", "框架")):
            detected = "overview"

        # ── diagnosis 检测 ──
        if not detected and any(kw in msg for kw in DIAG_ROOTS):
            detected = "diagnosis"

        if detected is not None and agent_name is not None:
            allowed = cls._AGENT_SUB_TYPES.get(agent_name, frozenset())
            if detected not in allowed:
                return None
        return detected

    # ── LLM 兜底路由 ──

    async def _llm_route(self, topic: str) -> RouteDecision:
        """LLM 路由决策 — 处理规则覆盖不了的表达。

        触发场景:
          - 口语/方言表达（"咋整" "不行了" "搞不定"）
          - 中英混杂无关键词命中
          - 极短模糊输入（"神经网络"）
          - 规则编译后仍然不确定的多意图输入
        """
        try:
            llm = self._get_llm()

            system_prompt = (
                "你是一个技术资源路由决策器。分析用户想要什么类型的资源，"
                "从以下 6 种中选择最合适的一个。\n\n"
                "判断依据:\n"
                "- 表达困惑/报错/不收敛/不行/急/怎么办 → code（代码诊断修复）\n"
                "- 要求解释概念/对比/原理/是什么 → content（技术文档）\n"
                "- 要求写代码/实现/demo/示例 → code（代码实操案例）\n"
                "- 要求做项目/实战/练手 → project（微型练习项目）\n"
                "- 要求可视化/动画/图解 → interactive_diagram（交互式可视化）\n"
                "- 要求梳理/归纳/框架/思维导图 → mindmap（思维导图）\n"
                "- 要求背诵/记忆/速记/考点 → flashcard（记忆闪卡）\n"
                "- 不确定时选择 content（默认）"
            )
            agent_options = "\n".join(
                f"- {k}: {v}" for k, v in {
                    "content": "课程文档/讲解（默认，适合解释概念、对比分析）",
                    "interactive_diagram": "交互式可视化演示（D3.js/SVG动画）",
                    "code": "代码实操案例 + 报错诊断修复",
                    "project": "微型练习项目（含里程碑、技术栈）",
                    "mindmap": "思维导图/概念框架",
                    "flashcard": "记忆闪卡（问答对）",
                }.items()
            )
            user_prompt = (
                f"学生消息: {topic}\n\n"
                f"可选资源类型:\n{agent_options}\n\n"
                f"请输出 JSON: {{\"agent\": \"<类型>\", \"rationale\": \"<一句话原因>\"}}\n"
                f"只输出 JSON，不要其他内容。"
            )

            messages = [{"role": "user", "content": user_prompt}]
            raw = await llm.chat(messages, system_prompt=system_prompt)

            from app.utils.json_parser import parse_llm_json

            result = parse_llm_json(raw, fallback={})
            agent = result.get("agent", DEFAULT_AGENT)
            if agent not in SUPPORTED_AGENTS:
                agent = DEFAULT_AGENT

            return RouteDecision(
                agent_name=agent,
                sub_type=self._detect_sub_type(topic, agent),
                rationale=result.get("rationale", "LLM 路由决策"),
                strategy="llm",
            )
        except Exception as e:
            logger.warning(f"LLM routing failed: {e}, using default agent")
            return RouteDecision(
                agent_name=DEFAULT_AGENT,
                rationale=f"LLM 路由失败回退: {e}",
                strategy="llm",
            )
