"""ResourceGenWorkflow — 模块化单 Agent 资源生成工作流

设计原则：
  - Director 意图分类 → 路由到**单个** Agent 生成
  - 用户说「生成 CNN 代码」→ 只出代码，不出全家桶
  - 显式要求「完整学习资料包」时才走多 Agent（未来扩展）

3 阶段流水线:
  Stage 1: plan（可选，仅 content/mindmap 需要大纲）
  Stage 2: generate → 单 Agent 执行
  Stage 3: finalize → 聚合结果

裁掉的 Agent:
  - ReadingAgent: 虚假引用，不产出实质性内容
  - ExerciseAgent: 练习中心已有完整闭环

接入的 Agent:
  - InteractiveDiagramAgent: 交互式可视化（新建）
  - ProjectAgent: 微型项目实战（已有，接入路由）
"""

import asyncio
import logging
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from app.agents.content_agent import ContentAgent
from app.agents.code_agent import CodeAgent
from app.agents.mindmap_agent import MindMapAgent
from app.agents.flashcard_agent import FlashCardAgent
from app.agents.project_agent import ProjectAgent
from app.agents.interactive_diagram_agent import InteractiveDiagramAgent
from app.orchestration.director import Director
from app.services.llm_service import (
    PROFILE_CONTENT,
    PROFILE_CODE,
    PROFILE_MINDMAP,
    PROFILE_FLASHCARD,
    PROFILE_DIRECTOR,
    PROFILE_INTERACTIVE_DIAGRAM,
    PROFILE_PROJECT,
)
from app.events.types import (
    StreamEvent, stage_start, stage_end, error_event, done_event,
)
from app.workflows.base_workflow import BaseWorkflow

logger = logging.getLogger(__name__)

# 需要大纲规划的 Agent
PLAN_REQUIRED_AGENTS = frozenset({"content", "mindmap"})

AGENT_LABELS: dict[str, str] = {
    "content": "课程文档",
    "interactive_diagram": "交互式可视化",
    "code": "代码案例",
    "project": "项目实战",
    "mindmap": "思维导图",
    "flashcard": "记忆闪卡",
}


class ResourceGenState(TypedDict, total=False):
    user_id: int
    topic: str
    resource_type: str
    sub_type: str | None
    student_profile: dict
    outline: dict
    content_blocks: list[dict]
    questions: list[dict]
    response: str
    error: str
    event_queue: Any  # asyncio.Queue[StreamEvent]
    # 内部路由信息
    agent_name: str


class ResourceGenWorkflow(BaseWorkflow):
    """资源生成工作流 — 单 Agent 模块化调度"""

    def __init__(self, use_mock: bool = False):
        super().__init__(use_mock=use_mock)
        self.content_agent = ContentAgent(
            use_mock_llm=use_mock, model_profile=PROFILE_CONTENT
        )
        self.code_agent = CodeAgent(
            use_mock_llm=use_mock, model_profile=PROFILE_CODE
        )
        self.mindmap_agent = MindMapAgent(
            use_mock_llm=use_mock, model_profile=PROFILE_MINDMAP
        )
        self.flashcard_agent = FlashCardAgent(
            use_mock_llm=use_mock, model_profile=PROFILE_FLASHCARD
        )
        self.project_agent = ProjectAgent(
            use_mock_llm=use_mock, model_profile=PROFILE_PROJECT
        )
        self.interactive_diagram_agent = InteractiveDiagramAgent(
            use_mock_llm=use_mock, model_profile=PROFILE_INTERACTIVE_DIAGRAM
        )
        self.director = Director(use_mock=use_mock, model_profile=PROFILE_DIRECTOR)

        self._agent_map: dict[str, Any] = {
            "content": self.content_agent,
            "interactive_diagram": self.interactive_diagram_agent,
            "code": self.code_agent,
            "project": self.project_agent,
            "mindmap": self.mindmap_agent,
            "flashcard": self.flashcard_agent,
        }

    @staticmethod
    def _emit(state: dict, event: StreamEvent) -> None:
        q = state.get("event_queue")
        if q is not None:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def _build_graph(self):
        graph = StateGraph(ResourceGenState)

        graph.add_node("plan", self._plan_node)
        graph.add_node("generate", self._generate_node)
        graph.add_node("finalize", self._finalize_node)

        graph.set_entry_point("plan")
        graph.add_edge("plan", "generate")
        graph.add_edge("generate", "finalize")
        graph.add_edge("finalize", END)

        return graph.compile()

    # ═══════════════════════════════════════════════════════════════
    # Stage 1: 路由 + 可选大纲规划
    # ═══════════════════════════════════════════════════════════════

    async def _plan_node(self, state: ResourceGenState) -> dict:
        topic = state.get("topic", "")
        resource_type = state.get("resource_type", "")
        student_profile = state.get("student_profile", {})

        # ── Director 路由 ──
        decision = await self.director.route(
            topic,
            resource_type=resource_type or None,
            student_profile=student_profile,
        )
        agent_name = decision.agent_name
        sub_type = decision.sub_type

        label = AGENT_LABELS.get(agent_name, agent_name)
        self._emit(state, stage_start("plan",
            f"识别意图：{decision.rationale}，准备生成{label}..."))

        logger.info(
            f"Director routed '{topic}' → {agent_name}"
            f" (strategy={decision.strategy}, sub_type={sub_type})"
        )

        # ── 需要大纲的 Agent：运行 ContentAgent._plan_node ──
        outline: dict = {}
        if agent_name in PLAN_REQUIRED_AGENTS:
            self._emit(state, stage_start("outline",
                f"正在分析「{topic}」的知识点结构..."))
            try:
                plan_result = await self.content_agent.plan_outline(
                    topic, student_profile,
                )
                outline = plan_result.get("outline", {})
                sub_count = len(outline.get("subsections", []))
                self._emit(state, stage_end("outline",
                    f"大纲规划完成，共 {sub_count} 个章节"))
            except Exception as e:
                logger.error(f"Outline planning failed: {e}")
                self._emit(state, error_event("outline", "大纲规划失败，使用默认结构"))

        self._emit(state, stage_end("plan",
            f"已选定 {label} 生成器，准备开始..."))

        return {
            "agent_name": agent_name,
            "sub_type": sub_type,
            "outline": outline,
            "resource_type": resource_type,
        }

    # ═══════════════════════════════════════════════════════════════
    # Stage 2: 单 Agent 生成
    # ═══════════════════════════════════════════════════════════════

    async def _generate_node(self, state: ResourceGenState) -> dict:
        topic = state.get("topic", "")
        student_profile = state.get("student_profile", {})
        outline = state.get("outline", {})
        agent_name = state.get("agent_name", "content")
        sub_type = state.get("sub_type")

        label = AGENT_LABELS.get(agent_name, agent_name)
        agent = self._agent_map.get(agent_name)
        if agent is None:
            logger.error(f"Unknown agent: {agent_name}, falling back to content")
            agent = self.content_agent
            agent_name = "content"

        self._emit(state, stage_start("generate", f"正在生成{label}，请稍后..."))

        try:
            agent_state = self._build_agent_state(
                agent_name, topic, student_profile, outline, sub_type,
            )
            result = await agent.run(agent_state)
        except Exception as e:
            logger.exception(f"Agent '{agent_name}' generation failed, falling back to ContentAgent")
            self._emit(state, error_event("generate", f"{label}生成失败，尝试回退到课程文档"))
            try:
                fallback_state = self._build_agent_state(
                    "content", topic, student_profile, outline, None,
                )
                result = await self.content_agent.run(fallback_state)
                result["response"] = f"{label}暂时不可用，已为您生成课程文档: " + result.get("response", "")
            except Exception as fb_e:
                logger.exception(f"ContentAgent fallback also failed: {fb_e}")
                result = {"blocks": [], "response": f"{label}生成失败，请稍后重试"}

        blocks = result.get("blocks", []) if isinstance(result, dict) else []
        response = result.get("response", "") if isinstance(result, dict) else str(result)

        self._emit(state, stage_end("generate",
            f"{label}完成" + (f"，共 {len(blocks)} 个内容块" if blocks else "")))

        logger.info(
            f"Agent '{agent_name}' generated {len(blocks)} blocks"
            + (f" (sub_type={sub_type})" if sub_type else "")
            + f" for topic '{topic}'"
        )

        return {
            "content_blocks": blocks,
            "response": response,
            "questions": result.get("questions", []) if isinstance(result, dict) else [],
        }

    def _build_agent_state(
        self, agent_name: str, topic: str,
        student_profile: dict, outline: dict,
        sub_type: str | None,
    ) -> dict:
        """构建各 Agent 所需的状态字典。"""
        base = {"topic": topic, "student_profile": student_profile}

        if agent_name == "content":
            base["outline"] = outline
            if sub_type == "comparison":
                base["comparison"] = True
        elif agent_name == "mindmap":
            base["outline"] = outline
        elif agent_name == "code":
            base["outline"] = outline
            if sub_type == "diagnosis":
                base["diagnosis"] = True
        elif agent_name == "project":
            base["prerequisites"] = self._build_prerequisites(student_profile)
        elif agent_name == "interactive_diagram":
            base["diagram_type"] = self._infer_diagram_type(topic)
        elif agent_name == "flashcard":
            base["student_profile"] = student_profile

        return base

    @staticmethod
    def _build_prerequisites(student_profile: dict) -> str:
        """从学生画像构建前置知识摘要。"""
        parts = []
        knowledge = student_profile.get("knowledge_base", 0)
        if knowledge:
            level = "beginner" if knowledge < 40 else "intermediate" if knowledge < 70 else "advanced"
            parts.append(f"学生水平: {level}")
        weak = student_profile.get("weak_points", [])
        if weak:
            parts.append(f"薄弱点: {', '.join(weak)}")
        strong = student_profile.get("strong_points", [])
        if strong:
            parts.append(f"已掌握: {', '.join(strong)}")
        return "; ".join(parts) if parts else "未知"

    @staticmethod
    def _infer_diagram_type(topic: str) -> str:
        """从 topic 关键词推断合适的图表类型。"""
        t = topic.lower()
        if any(kw in t for kw in ("注意力", "attention", "self-attention", "transformer")):
            return "attention"
        if any(kw in t for kw in ("训练", "training", "epoch", "loss", "收敛", "梯度")):
            return "training_dynamics"
        if any(kw in t for kw in ("特征", "feature", "pca", "t-sne", "聚类", "降维", "决策边界")):
            return "feature_space"
        if any(kw in t for kw in ("步骤", "算法", "algorithm", "流程", "过程", "伪代码")):
            return "algorithm"
        return "architecture"

    # ═══════════════════════════════════════════════════════════════
    # Stage 3: Finalize
    # ═══════════════════════════════════════════════════════════════

    async def _finalize_node(self, state: ResourceGenState) -> dict:
        content_blocks = state.get("content_blocks", [])
        questions = state.get("questions", [])
        response = state.get("response", "")
        topic = state.get("topic", "")
        agent_name = state.get("agent_name", "content")
        label = AGENT_LABELS.get(agent_name, agent_name)

        self._emit(state, stage_start("finalize", "正在汇总生成结果..."))

        if not response and content_blocks:
            response = f"已为您生成「{topic}」的{label}，共 {len(content_blocks)} 个内容块。"
        elif not response:
            response = f"「{topic}」的{label}已生成完成。"

        self._emit(state, stage_end("finalize",
            f"{label}已就绪" + (f"，共 {len(content_blocks)} 个内容块" if content_blocks else "")))

        return {
            "response": response,
            "content_blocks": content_blocks,
            "questions": questions,
        }
