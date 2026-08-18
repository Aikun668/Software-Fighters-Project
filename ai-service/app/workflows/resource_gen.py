"""ResourceGenWorkflow — 资源生成工作流（带质量门控）

设计原则：
  - Director 意图分类 → 路由到**单个** Agent 生成
  - 用户说「生成 CNN 代码」→ 只出代码，不出全家桶
  - 显式要求「完整学习资料包」时才走多 Agent（未来扩展）

有界质量门控（首版仅 content / interactive_diagram）：
  plan → generate → validate → review → repair(最多一次) → finalize
  quality_mode:
    - off    : 跳过质量门控，行为等价基线
    - shadow : 记录 Validator/Judge 结论，但不触发修复或降级
    - active : 允许一次 Repair，结构失败走内容降级
"""

import asyncio
import logging
import time
import uuid
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
from app.services.resource_quality_gate import (
    ResourceValidator,
    ResourceReviewService,
)
from app.events.types import (
    StreamEvent, stage_start, stage_end, error_event, done_event,
)
from app.workflows.base_workflow import BaseWorkflow

logger = logging.getLogger(__name__)

# 需要大纲规划的 Agent
PLAN_REQUIRED_AGENTS = frozenset({"content", "mindmap"})

# 首版启用质量门控（Validator + Judge）的 Agent
QUALITY_GATED_AGENTS = frozenset({"content", "interactive_diagram"})

AGENT_LABELS: dict[str, str] = {
    "content": "技术文档",
    "interactive_diagram": "交互式可视化",
    "code": "代码案例",
    "project": "项目实战",
    "mindmap": "思维导图",
    "flashcard": "记忆闪卡",
}

QUALITY_MODES = frozenset({"off", "shadow", "active"})


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
    route_strategy: str
    run_id: str
    # 质量门控
    draft_blocks: list[dict]
    validation_result: dict
    review_status: str
    review_reason: str
    repair_instructions: list[str]
    repair_attempted: bool
    pre_repair_blocks: list[dict]
    fallback_used: bool
    final_status: str
    error_type: str
    diagram_source: str
    diagram_schema_version: str
    stage_timings: dict[str, float]


class ResourceGenWorkflow(BaseWorkflow):
    """资源生成工作流 — 单 Agent 模块化调度 + 有界质量门控"""

    def __init__(
        self,
        use_mock: bool = False,
        validator=None,
        reviewer=None,
        quality_mode: str = "shadow",
    ):
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

        if quality_mode not in QUALITY_MODES:
            raise ValueError(
                f"quality_mode must be one of {sorted(QUALITY_MODES)}, got {quality_mode!r}"
            )
        self.quality_mode = quality_mode
        self.validator = validator if validator is not None else ResourceValidator()
        self.reviewer = (
            reviewer if reviewer is not None else ResourceReviewService(use_mock=use_mock)
        )

    @staticmethod
    def _emit(state: dict, event: StreamEvent) -> None:
        q = state.get("event_queue")
        if q is not None:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def _with_stage_timing(self, state: dict, stage: str, started_at: float, update: dict) -> dict:
        timings = dict(state.get("stage_timings", {}))
        timings[stage] = round((time.perf_counter() - started_at) * 1000, 2)
        return {**update, "stage_timings": timings}

    def _build_graph(self):
        graph = StateGraph(ResourceGenState)

        graph.add_node("plan", self._plan_node)
        graph.add_node("generate", self._generate_node)
        graph.add_node("validate", self._validate_node)
        graph.add_node("review", self._review_node)
        graph.add_node("repair", self._repair_node)
        graph.add_node("fallback", self._fallback_node)
        graph.add_node("finalize", self._finalize_node)

        graph.set_entry_point("plan")
        graph.add_edge("plan", "generate")
        graph.add_edge("generate", "validate")
        graph.add_conditional_edges("validate", self._after_validate, {
            "review": "review",
            "repair": "repair",
            "fallback": "fallback",
            "finalize": "finalize",
        })
        graph.add_conditional_edges("review", self._after_review, {
            "repair": "repair",
            "finalize": "finalize",
        })
        graph.add_edge("repair", "validate")
        graph.add_edge("fallback", "finalize")
        graph.add_edge("finalize", END)

        return graph.compile()

    # ═══════════════════════════════════════════════════════════════
    # Stage 1: 路由 + 可选大纲规划
    # ═══════════════════════════════════════════════════════════════

    async def _plan_node(self, state: ResourceGenState) -> dict:
        started = time.perf_counter()
        topic = state.get("topic", "")
        resource_type = state.get("resource_type", "")
        student_profile = state.get("student_profile", {})

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

        outline: dict = {}
        if agent_name in PLAN_REQUIRED_AGENTS:
            self._emit(state, stage_start("outline",
                f"正在分析「{topic}」的知识点结构..."))
            try:
                plan_result = await self.content_agent.plan_outline(
                    topic, student_profile,
                )
                outline = plan_result.get("outline", {})
                sub_count = len(outline.get("subsections") or outline.get("sections") or outline.get("steps") or [])
                self._emit(state, stage_end("outline",
                    f"大纲规划完成，共 {sub_count} 个章节"))
            except Exception as e:
                logger.error(f"Outline planning failed: {e}")
                self._emit(state, error_event("outline", "大纲规划失败，使用默认结构"))

        self._emit(state, stage_end("plan",
            f"已选定 {label} 生成器，准备开始..."))

        run_id = state.get("run_id") or uuid.uuid4().hex[:12]
        return self._with_stage_timing(state, "plan", started, {
            "agent_name": agent_name,
            "sub_type": sub_type,
            "outline": outline,
            "resource_type": resource_type,
            "route_strategy": decision.strategy,
            "run_id": run_id,
            "repair_attempted": False,
            "fallback_used": False,
        })

    # ═══════════════════════════════════════════════════════════════
    # Stage 2: 单 Agent 生成（草稿写入 draft_blocks）
    # ═══════════════════════════════════════════════════════════════

    async def _run_specialist(
        self, state: ResourceGenState, agent_name: str,
        repair_instructions: list[str] | None = None,
        previous_blocks: list[dict] | None = None,
    ) -> dict:
        """构建 Agent state，必要时附加修复说明与原草稿，并标准化 blocks/response。"""
        topic = state.get("topic", "")
        student_profile = state.get("student_profile", {})
        outline = state.get("outline", {})
        sub_type = state.get("sub_type")

        agent = self._agent_map.get(agent_name)
        if agent is None:
            logger.error(f"Unknown agent: {agent_name}, falling back to content")
            agent = self.content_agent
            agent_name = "content"

        agent_state = self._build_agent_state(
            agent_name, topic, student_profile, outline, sub_type,
        )
        if repair_instructions:
            agent_state["repair_instructions"] = repair_instructions
        if previous_blocks:
            agent_state["previous_blocks"] = previous_blocks

        result = await agent.run(agent_state)
        blocks = (result.get("blocks") or result.get("content_blocks") or []) if isinstance(result, dict) else []
        response = result.get("response", "") if isinstance(result, dict) else str(result)
        questions = result.get("questions", []) if isinstance(result, dict) else []

        return {
            "blocks": blocks,
            "response": response,
            "questions": questions,
            "agent_name": agent_name,
            "diagram_source": result.get("diagram_source", "") if isinstance(result, dict) else "",
            "diagram_schema_version": result.get("diagram_schema_version", "") if isinstance(result, dict) else "",
        }

    async def _generate_node(self, state: ResourceGenState) -> dict:
        started = time.perf_counter()
        topic = state.get("topic", "")
        agent_name = state.get("agent_name", "content")

        label = AGENT_LABELS.get(agent_name, agent_name)
        self._emit(state, stage_start("generate", f"正在生成{label}，请稍后..."))

        try:
            result = await self._run_specialist(state, agent_name)
        except Exception as e:
            logger.exception(f"Agent '{agent_name}' generation failed, falling back to ContentAgent")
            self._emit(state, error_event("generate", f"{label}生成失败，尝试回退到课程文档"))
            try:
                result = await self._run_specialist(state, "content", None)
                result["response"] = f"{label}暂时不可用，已为您生成课程文档: " + result.get("response", "")
                agent_name = "content"
            except Exception as fb_e:
                logger.exception(f"ContentAgent fallback also failed: {fb_e}")
                result = {"blocks": [], "response": f"{label}生成失败，请稍后重试", "questions": []}

        blocks = result.get("blocks", [])
        response = result.get("response", "")
        questions = result.get("questions", [])

        self._emit(state, stage_end("generate",
            f"{label}完成" + (f"，共 {len(blocks)} 个内容块" if blocks else "")))

        logger.info(
            f"Agent '{agent_name}' generated {len(blocks)} blocks for topic '{topic}'"
        )

        return self._with_stage_timing(state, "generate", started, {
            "draft_blocks": blocks,
            "response": response,
            "questions": questions,
            "agent_name": agent_name,
            "diagram_source": result.get("diagram_source", ""),
            "diagram_schema_version": result.get("diagram_schema_version", ""),
        })

    # ═══════════════════════════════════════════════════════════════
    # Stage 3: 质量门控（validate → review → repair/fallback）
    # ═══════════════════════════════════════════════════════════════

    async def _validate_node(self, state: ResourceGenState) -> dict:
        started = time.perf_counter()
        if self.quality_mode == "off":
            return {}
        draft_blocks = state.get("draft_blocks", [])
        agent_name = state.get("agent_name", "content")
        self._emit(state, stage_start("validate", "正在校验生成结果结构..."))
        result = self.validator.validate(agent_name, draft_blocks)
        validation_result = {
            "passed": result.passed,
            "reason": result.reason,
            "issues": result.issues,
        }
        self._emit(state, stage_end("validate",
            "结构校验通过" if result.passed else "结构校验未通过"))
        return self._with_stage_timing(state, "validate", started, {
            "validation_result": validation_result,
        })

    def _after_validate(self, state: ResourceGenState) -> str:
        if self.quality_mode == "off":
            return "finalize"
        validation_result = state.get("validation_result") or {}
        if validation_result.get("passed", True):
            return "review"
        if self.quality_mode == "active":
            return "fallback" if state.get("repair_attempted") else "repair"
        # shadow：只记录，不干预
        return "review"

    async def _review_node(self, state: ResourceGenState) -> dict:
        started = time.perf_counter()
        agent_name = state.get("agent_name", "content")
        if agent_name not in QUALITY_GATED_AGENTS:
            return self._with_stage_timing(state, "review", started, {
                "review_status": "not_applicable",
                "review_reason": "该资源类型未启用 Judge",
            })

        topic = state.get("topic", "")
        draft_blocks = state.get("draft_blocks", [])
        student_profile = state.get("student_profile", {})
        self._emit(state, stage_start("review", "正在进行质量评审..."))
        try:
            decision = await self.reviewer.review(
                topic, agent_name, draft_blocks, student_profile,
            )
            update = {
                "review_status": decision.status,
                "review_reason": decision.reason,
                "repair_instructions": decision.fixes,
            }
        except Exception as e:
            logger.exception(f"Reviewer failed for agent '{agent_name}'")
            update = {
                "review_status": "skipped",
                "review_reason": "Judge 不可用",
                "repair_instructions": [],
            }
        self._emit(state, stage_end("review", f"评审完成：{update['review_status']}"))
        return self._with_stage_timing(state, "review", started, update)

    def _after_review(self, state: ResourceGenState) -> str:
        if (
            self.quality_mode == "active"
            and state.get("review_status") == "repair"
            and not state.get("repair_attempted")
        ):
            return "repair"
        return "finalize"

    async def _repair_node(self, state: ResourceGenState) -> dict:
        started = time.perf_counter()
        agent_name = state.get("agent_name", "content")
        label = AGENT_LABELS.get(agent_name, agent_name)
        instructions = state.get("repair_instructions", [])
        pre_blocks = state.get("draft_blocks", [])
        self._emit(state, stage_start("repair", f"根据评审建议修复{label}..."))
        try:
            result = await self._run_specialist(state, agent_name, instructions, pre_blocks)
            update = {
                "pre_repair_blocks": pre_blocks,
                "draft_blocks": result["blocks"],
                "response": result["response"],
                "questions": result.get("questions", []),
                "repair_attempted": True,
                "diagram_source": result.get("diagram_source", ""),
                "diagram_schema_version": result.get("diagram_schema_version", ""),
            }
        except Exception as e:
            logger.exception(f"Repair failed for agent '{agent_name}'")
            self._emit(state, error_event("repair", "修复失败，保留原草稿"))
            update = {"repair_attempted": True}
        self._emit(state, stage_end("repair", "修复完成"))
        return self._with_stage_timing(state, "repair", started, update)

    async def _fallback_node(self, state: ResourceGenState) -> dict:
        started = time.perf_counter()
        topic = state.get("topic", "")
        self._emit(state, stage_start("fallback", "生成受限，切换到课程文档降级..."))
        try:
            result = await self._run_specialist(state, "content", None)
            blocks = result["blocks"]
            vr = self.validator.validate("content", blocks)
            if vr.passed:
                update = {
                    "draft_blocks": blocks,
                    "response": result["response"],
                    "questions": result.get("questions", []),
                    "fallback_used": True,
                }
            else:
                update = {
                    "draft_blocks": blocks,
                    "response": result["response"],
                    "questions": result.get("questions", []),
                    "fallback_used": True,
                    "final_status": "error",
                    "error": f"「{topic}」的资源生成失败，请稍后重试",
                    "error_type": "fallback_invalid",
                }
        except Exception as e:
            logger.exception(f"Fallback content generation failed: {e}")
            self._emit(state, error_event("fallback", "降级生成失败"))
            update = {
                "draft_blocks": [],
                "response": f"「{topic}」的资源生成失败，请稍后重试",
                "fallback_used": True,
                "final_status": "error",
                "error": f"「{topic}」的资源生成失败，请稍后重试",
                "error_type": "generation_failed",
            }
        self._emit(state, stage_end("fallback", "降级完成"))
        return self._with_stage_timing(state, "fallback", started, update)

    # ═══════════════════════════════════════════════════════════════
    # Stage 4: Finalize
    # ═══════════════════════════════════════════════════════════════

    async def _finalize_node(self, state: ResourceGenState) -> dict:
        started = time.perf_counter()
        draft_blocks = state.get("draft_blocks", [])
        questions = state.get("questions", [])
        response = state.get("response", "")
        topic = state.get("topic", "")
        agent_name = state.get("agent_name", "content")
        label = AGENT_LABELS.get(agent_name, agent_name)

        self._emit(state, stage_start("finalize", "正在汇总生成结果..."))

        if not response and draft_blocks:
            response = f"已为您生成「{topic}」的{label}，共 {len(draft_blocks)} 个内容块。"
        elif not response:
            response = f"「{topic}」的{label}已生成完成。"

        final_status = state.get("final_status") or "success"

        self._emit(state, stage_end("finalize",
            f"{label}已就绪" + (f"，共 {len(draft_blocks)} 个内容块" if draft_blocks else "")))

        return self._with_stage_timing(state, "finalize", started, {
            "content_blocks": draft_blocks,
            "response": response,
            "questions": questions,
            "final_status": final_status,
        })

    # ═══════════════════════════════════════════════════════════════
    # Agent state 构建工具
    # ═══════════════════════════════════════════════════════════════

    def _build_agent_state(
        self, agent_name: str, topic: str,
        student_profile: dict, outline: dict,
        sub_type: str | None,
    ) -> dict:
        """构建各 Agent 所需的状态字典。"""
        base = {"topic": topic, "student_profile": student_profile}

        if agent_name == "content":
            base["outline"] = outline
            base["sub_type"] = sub_type or "overview"
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

    # ── P1-2: 扩展图表类型推断规则（加权计分）──
    _DIAGRAM_TYPE_RULES: list[tuple[str, list[str]]] = [
        ("architecture", [
            "CNN", "卷积神经网络", "RNN", "循环神经网络", "LSTM", "GRU",
            "Transformer", "BERT", "GPT", "ResNet", "VGG", "U-Net",
            "encoder", "decoder", "编码器", "解码器",
            "网络结构", "模型架构", "层次结构", "层级", "组件",
            "整体结构", "总体框架", "系统架构", "框架图",
        ]),
        ("training_dynamics", [
            "训练", "training", "epoch", "loss", "损失函数", "损失",
            "收敛", "梯度", "学习率", "过拟合", "欠拟合",
            "accuracy", "准确率", "验证集", "训练曲线",
            "迭代", "iteration", "batch", "收敛曲线",
        ]),
        ("attention", [
            "注意力", "attention", "self-attention", "多头",
            "multi-head", "QKV", "query", "key", "value",
            "softmax", "token", "embedding", "位置编码",
            "注意力机制", "注意力权重", "自注意力",
        ]),
        ("feature_space", [
            "特征", "feature", "PCA", "t-SNE", "降维",
            "聚类", "决策边界", "分布", "散点图",
            "特征空间", "特征提取", "可视化", "嵌入",
            "embedding", "高维", "流形",
        ]),
        ("algorithm", [
            "步骤", "算法", "algorithm", "流程", "过程", "伪代码",
            "前向传播", "反向传播", "backprop", "BP",
            "梯度下降", "SGD", "Adam", "dropout",
            "batch norm", "池化", "pooling", "激活函数",
            "ReLU", "sigmoid", "tanh", "softmax",
        ]),
    ]

    @classmethod
    def _infer_diagram_type(cls, topic: str) -> str:
        """从 topic 关键词加权计分推断最合适的图表类型。"""
        t = topic.lower()
        scores: dict[str, int] = {}
        for dtype, keywords in cls._DIAGRAM_TYPE_RULES:
            score = 0
            for kw in keywords:
                if kw.lower() in t:
                    score += 1
            if score > 0:
                scores[dtype] = score

        if not scores:
            return "architecture"

        # 取最高分，同分时 architecture 优先（最常见场景）
        best = max(scores, key=lambda k: (scores[k], k == "architecture"))
        return best
