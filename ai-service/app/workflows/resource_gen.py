"""
ResourceGenWorkflow — 多 Agent 协同资源生成工作流

借鉴 OpenMAIC Director+Worker LangGraph 循环 + DeepTutor repair sub-loop：
  Stage 1: 大纲规划（ContentAgent._plan_node）
  Stage 2: Director 动态路由 → 选择 Agent 子集
  Stage 3: ContentAgent 先跑 → Whiteboard → 选中 Agent 并行生成
  Stage 4: 收集 AgentTurnSummary → peer context
  Stage 5: 质量审查 → 通过则结束，失败则 redo（max 2 轮）

Director 支持 3 路由策略:
  - rule fast-path: 关键词匹配（80%+ 覆盖，零延迟）
  - profile filter: kb < 30 跳过 code, visual learner 必加 mindmap
  - LLM fallback: 无关键词匹配时才用

Architecture #2: 纯 AI 生成。不再持久化（Java 从 done event 提取结果后自行保存）。
"""

import asyncio
import logging
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from app.agents.content_agent import ContentAgent
from app.agents.exercise_agent import ExerciseAgent
from app.agents.flashcard_agent import FlashCardAgent
from app.agents.mindmap_agent import MindMapAgent
from app.agents.reading_agent import ReadingAgent
from app.agents.code_agent import CodeAgent
from app.orchestration.agent_bus import AgentBus
from app.orchestration.director import Director
from app.services.llm_service import (
    PROFILE_CONTENT,
    PROFILE_EXERCISE,
    PROFILE_CODE,
    PROFILE_MINDMAP,
    PROFILE_READING,
    PROFILE_FLASHCARD,
    PROFILE_DIRECTOR,
)
from app.orchestration.agent_turn_summary import AgentTurnSummary
from app.events.types import (
    StreamEvent, stage_start, stage_end, error_event, done_event,
)
from app.workflows.base_workflow import BaseWorkflow
from app.workflows.resource_whiteboard import ResourceWhiteboard

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 2
AGENT_TIMEOUT = 30.0  # 单个 Agent 执行超时（秒）
DEFAULT_AGENTS = ["content", "exercise", "mindmap", "reading", "code", "flashcard"]


class ResourceGenState(TypedDict, total=False):
    user_id: int
    topic: str
    student_profile: dict
    outline: dict
    content_blocks: list[dict]
    questions: list[dict]
    resource_ids: list[int]
    response: str
    error: str
    # ── Director Loop 扩展 ──
    agent_set: list[str]
    iteration: int
    peer_context: str
    turn_summaries: list[dict]
    quality_result: dict
    # ── Inquiry 层传递 ──
    suggested_types: list[str]
    # ── 进度事件队列 ──
    event_queue: Any  # asyncio.Queue[StreamEvent]


class ResourceGenWorkflow(BaseWorkflow):
    """资源生成工作流 — Director Loop 编排动态 Agent 集合"""

    def __init__(self, use_mock: bool = False):
        super().__init__(use_mock=use_mock)
        self.content_agent = ContentAgent(
            use_mock_llm=use_mock, model_profile=PROFILE_CONTENT
        )
        self.exercise_agent = ExerciseAgent(
            use_mock_llm=use_mock, model_profile=PROFILE_EXERCISE
        )
        self.mindmap_agent = MindMapAgent(
            use_mock_llm=use_mock, model_profile=PROFILE_MINDMAP
        )
        self.reading_agent = ReadingAgent(
            use_mock_llm=use_mock, model_profile=PROFILE_READING
        )
        self.code_agent = CodeAgent(
            use_mock_llm=use_mock, model_profile=PROFILE_CODE
        )
        self.flashcard_agent = FlashCardAgent(
            use_mock_llm=use_mock, model_profile=PROFILE_FLASHCARD
        )
        self.director = Director(use_mock=use_mock, model_profile=PROFILE_DIRECTOR)
        self.bus = AgentBus()

    @staticmethod
    def _emit(state: dict, event: StreamEvent) -> None:
        """Push an event into the queue if present (fire-and-forget)."""
        q = state.get("event_queue")
        if q is not None:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # non-critical, drop silently

    def _build_graph(self):
        graph = StateGraph(ResourceGenState)

        graph.add_node("plan", self._plan_node)
        graph.add_node("director", self._director_node)
        graph.add_node("generate", self._generate_node)
        graph.add_node("collect_summaries", self._collect_summaries_node)
        graph.add_node("review", self._review_node)
        graph.add_node("finalize", self._finalize_node)

        graph.set_entry_point("plan")
        graph.add_edge("plan", "director")
        graph.add_edge("director", "generate")
        graph.add_edge("generate", "collect_summaries")
        graph.add_edge("collect_summaries", "review")

        graph.add_conditional_edges(
            "review",
            self._route_after_review,
            {
                "finalize": "finalize",
                "generate": "generate",
            },
        )

        graph.add_edge("finalize", END)

        return graph.compile()

    # ═══════════════════════════════════════════════════════════════
    # Stage 1: 大纲规划
    # ═══════════════════════════════════════════════════════════════

    async def _plan_node(self, state: ResourceGenState) -> dict:
        topic = state.get("topic", "")
        student_profile = state.get("student_profile", {})

        self._emit(state, stage_start("plan",
            f"正在分析「{topic}」的知识点结构，请稍后..."))

        content_state = {
            "topic": topic,
            "student_profile": student_profile,
        }
        result = await self.content_agent._plan_node(content_state)
        outline = result.get("outline", {})
        sub_count = len(outline.get("subsections", []))

        self._emit(state, stage_end("plan",
            f"大纲规划完成，共 {sub_count} 个章节"))

        logger.info(
            f"Outline generated for topic '{topic}': "
            f"{sub_count} subsections"
        )
        return {"outline": outline, "iteration": state.get("iteration", 0)}

    # ═══════════════════════════════════════════════════════════════
    # Stage 2: Director 动态路由
    # ═══════════════════════════════════════════════════════════════

    async def _director_node(self, state: ResourceGenState) -> dict:
        topic = state.get("topic", "")
        student_profile = state.get("student_profile", {})
        iteration = state.get("iteration", 0)
        suggested_types = state.get("suggested_types", [])

        self._emit(state, stage_start("director",
            "正在决定最优资源组合，请稍后..."))

        # Director 仅在首轮决策，retry 复用相同 agent_set
        if iteration == 0:
            # ── Inquiry 层快车道：上游已确定 agent 子集，跳过路由 ──
            if suggested_types:
                agent_set = self.director.apply_profile_filter(
                    list(suggested_types), student_profile,
                )
                logger.info(
                    f"Director using inquiry suggested_types for '{topic}': "
                    f"{agent_set} (from suggested={suggested_types})"
                )
            else:
                decision = await self.director.route(topic, student_profile)
                agent_set = decision.selected_agents
                logger.info(
                    f"Director routing for '{topic}': "
                    f"{agent_set} (strategy={decision.strategy}, "
                    f"rationale={decision.rationale})"
                )
        else:
            agent_set = state.get("agent_set", DEFAULT_AGENTS)
            logger.info(
                f"Director reusing agent_set for iteration {iteration}: {agent_set}"
            )

        self._emit(state, stage_end("director",
            f"已选定 {len(agent_set)} 个智能体协同生成"))

        return {"agent_set": agent_set}

    # ═══════════════════════════════════════════════════════════════
    # Stage 3: 生成（ContentAgent 先 → 其他并行 + peer_context）
    # ═══════════════════════════════════════════════════════════════

    async def _generate_node(self, state: ResourceGenState) -> dict:
        topic = state.get("topic", "")
        student_profile = state.get("student_profile", {})
        outline = state.get("outline", {})
        agent_set = state.get("agent_set", DEFAULT_AGENTS)
        iteration = state.get("iteration", 0)
        peer_context = state.get("peer_context", "")

        self.bus.clear()

        # Step A: ContentAgent 始终先跑
        content_blocks, wb_context, content_result = await self._run_content_agent(
            state, topic, student_profile, outline,
        )

        # Step B: 动态选择并行 Agent 并执行
        agent_states = self._build_parallel_agent_states(
            topic, student_profile, outline, wb_context, content_blocks, peer_context,
        )
        results = await self._run_parallel_agents(
            state, agent_set, agent_states, content_result,
        )

        # Step C: 收集各 Agent 的 Turn Summary
        self._summarize_agent_results(topic, student_profile, results, agent_states)

        # Step D: 聚合 blocks + questions
        all_blocks, questions = self._aggregate_results(content_blocks, results)

        logger.info(
            f"Iteration {iteration}: generated {len(all_blocks)} blocks "
            f"+ {len(questions)} questions for '{topic}' "
            f"(agents: {list(results.keys())})"
        )

        return {
            "content_blocks": all_blocks,
            "questions": questions,
            "iteration": iteration + 1,
        }

    async def _run_content_agent(
        self, state: ResourceGenState, topic: str,
        student_profile: dict, outline: dict,
    ) -> tuple[list[dict], str, dict]:
        """Step A: 运行 ContentAgent 并构建 Whiteboard。"""
        self._emit(state, stage_start("content", f"正在生成课程文档，请稍后..."))

        content_state = {"topic": topic, "student_profile": student_profile, "outline": outline}
        try:
            content_result = await self.content_agent._generate_node(content_state)
        except Exception as e:
            logger.error(f"ContentAgent generation failed: {e}")
            content_result = {"blocks": [], "response": ""}
            self._emit(state, error_event("content", "课程文档生成失败"))

        if isinstance(content_result, dict):
            content_blocks = content_result.get("content_blocks", [])
            wb = ResourceWhiteboard.from_content_output(topic, outline, content_blocks)
        else:
            content_blocks = []
            wb = ResourceWhiteboard(topic=topic)

        self._emit(state, stage_end("content", f"课程文档完成，共 {len(content_blocks)} 个内容块"))
        wb_context = wb.to_context_text()

        content_summary = self.content_agent.create_turn_summary(content_state, content_result)
        self.bus.submit(content_summary)

        return content_blocks, wb_context, content_result

    def _build_parallel_agent_states(
        self, topic: str, student_profile: dict, outline: dict,
        wb_context: str, content_blocks: list[dict], peer_context: str,
    ) -> dict:
        """Step B prep: 构建并行 Agent 的状态字典。"""
        states = {
            "exercise": {"topic": topic, "count": 5, "difficulty": "medium",
                         "student_profile": student_profile},
            "mindmap": {"topic": topic, "student_profile": student_profile,
                        "outline": outline, "whiteboard_context": wb_context},
            "reading": {"topic": topic, "student_profile": student_profile,
                        "whiteboard_context": wb_context},
            "code": {"topic": topic, "student_profile": student_profile,
                     "outline": outline, "whiteboard_context": wb_context},
            "flashcard": {"topic": topic, "content_blocks": content_blocks},
        }
        if peer_context:
            for key in ["mindmap", "reading", "code"]:
                s = states[key]
                existing = s.get("peer_context", "")
                s["peer_context"] = f"{existing}\n{peer_context}" if existing else peer_context
        return states

    async def _run_parallel_agents(
        self, state: ResourceGenState, agent_set: list[str],
        agent_states: dict, content_result: dict,
    ) -> dict[str, dict]:
        """Step B: 并行启动 Agent 并收集结果。"""
        agent_map = {
            "exercise": self.exercise_agent, "mindmap": self.mindmap_agent,
            "reading": self.reading_agent, "code": self.code_agent,
            "flashcard": self.flashcard_agent,
        }
        agent_labels = {
            "mindmap": "思维导图", "exercise": "练习题",
            "reading": "拓展阅读", "code": "代码案例", "flashcard": "记忆闪卡",
        }
        results: dict[str, dict] = {"content": content_result}
        parallel_agents = [a for a in agent_set if a != "content"]

        if not parallel_agents:
            return results

        for idx, agent_name in enumerate(parallel_agents):
            label = agent_labels.get(agent_name, agent_name)
            self._emit(state, stage_start(agent_name,
                f"正在生成{label}（{idx + 1}/{len(parallel_agents)}），请稍后..."))

        tasks = {
            name: asyncio.ensure_future(agent_map[name].run(agent_states[name]))
            for name in parallel_agents
        }
        gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)

        for agent_name, result in zip(parallel_agents, gathered):
            label = agent_labels.get(agent_name, agent_name)
            if isinstance(result, asyncio.TimeoutError):
                logger.error(f"{agent_name} timed out after {AGENT_TIMEOUT}s")
                results[agent_name] = {}
                self._emit(state, error_event(agent_name, f"{label}生成超时"))
            elif isinstance(result, Exception):
                logger.error(f"{agent_name} generation failed: {result}")
                results[agent_name] = {}
                self._emit(state, error_event(agent_name, f"{label}生成失败"))
            else:
                results[agent_name] = result
                block_count = len(result.get("blocks", [])) if isinstance(result, dict) else 0
                self._emit(state, stage_end(agent_name,
                    f"{label}完成" + (f"，共 {block_count} 个块" if block_count else "")))
        return results

    def _summarize_agent_results(
        self, topic: str, student_profile: dict,
        results: dict[str, dict], agent_states: dict,
    ) -> None:
        """Step C: 为每个 Agent 结果创建 Turn Summary 并提交到 Bus。"""
        for agent_name, result in results.items():
            if isinstance(result, BaseException):
                continue
            if agent_name == "content":
                agent = self.content_agent
                s = {"topic": topic, "student_profile": student_profile}
            elif agent_name in agent_states:
                agent_map = {
                    "exercise": self.exercise_agent, "mindmap": self.mindmap_agent,
                    "reading": self.reading_agent, "code": self.code_agent,
                    "flashcard": self.flashcard_agent,
                }
                agent = agent_map.get(agent_name)
                if agent is None:
                    continue
                s = agent_states[agent_name]
            else:
                continue
            try:
                self.bus.submit(agent.create_turn_summary(s, result))
            except Exception as e:
                logger.warning(f"Failed to create turn summary for {agent_name}: {e}")

    @staticmethod
    def _aggregate_results(
        content_blocks: list[dict], results: dict[str, dict],
    ) -> tuple[list[dict], list[dict]]:
        """Step D: 聚合所有 content_blocks 和 questions。"""
        all_blocks = list(content_blocks)
        for label in ["mindmap", "reading", "code", "flashcard"]:
            r = results.get(label)
            if isinstance(r, dict):
                all_blocks.extend(r.get("blocks", []))

        exercise_result = results.get("exercise", {})
        questions = (
            exercise_result.get("questions", [])
            if isinstance(exercise_result, dict) else []
        )
        return all_blocks, questions

    # ═══════════════════════════════════════════════════════════════
    # Stage 4: 收集 AgentTurnSummary → peer context
    # ═══════════════════════════════════════════════════════════════

    async def _collect_summaries_node(
        self, state: ResourceGenState
    ) -> dict:
        """将 AgentBus 中的摘要序列化到 state，构建 peer_context"""
        self._emit(state, stage_start("summarize", "正在汇总各智能体结果，请稍后..."))

        all_summaries = self.bus.get_all_summaries()
        summaries = [s.to_dict() for s in all_summaries]

        peer_context = ""
        if all_summaries:
            peer_context = (
                AgentTurnSummary.build_peer_context_section(
                    "content", all_summaries
                )
            )

        self._emit(state, stage_end("summarize",
            f"汇总完成，共 {len(summaries)} 个智能体摘要"))

        logger.debug(
            f"Collected {len(summaries)} turn summaries, "
            f"peer_context length: {len(peer_context)}"
        )

        return {
            "turn_summaries": summaries,
            "peer_context": peer_context,
        }

    # ═══════════════════════════════════════════════════════════════
    # Stage 5: 质量审查（纯逻辑，无 LLM）
    # ═══════════════════════════════════════════════════════════════

    async def _review_node(self, state: ResourceGenState) -> dict:
        content_blocks = state.get("content_blocks", [])
        questions = state.get("questions", [])
        iteration = state.get("iteration", 0)

        self._emit(state, stage_start("review", "正在进行质量审查，请稍后..."))

        passed, feedback = self._quality_check(content_blocks, questions)

        quality_result = {
            "passed": passed,
            "feedback": feedback,
            "iteration": iteration,
            "block_count": len(content_blocks),
            "question_count": len(questions),
        }

        if passed:
            logger.info(
                f"Quality check PASSED at iteration {iteration}: "
                f"{len(content_blocks)} blocks, {len(questions)} questions"
            )
            self._emit(state, stage_end("review",
                f"质量审查通过，{len(content_blocks)} 个内容块，{len(questions)} 道题目"))
        else:
            logger.warning(
                f"Quality check FAILED at iteration {iteration}: {feedback}"
            )
            self._emit(state, stage_end("review",
                f"质量审查未通过，{feedback}，正在重新生成..."))

        return {"quality_result": quality_result, "iteration": iteration}

    @staticmethod
    def _route_after_review(state: ResourceGenState) -> str:
        quality = state.get("quality_result", {})
        iteration = state.get("iteration", 0)
        passed = quality.get("passed", True)

        if passed:
            return "finalize"

        if iteration < MAX_ITERATIONS:
            return "generate"

        logger.warning(
            f"Max iterations ({MAX_ITERATIONS}) reached, "
            f"finalizing despite quality failure"
        )
        return "finalize"

    # ═══════════════════════════════════════════════════════════════
    # Stage 6: Finalize — 聚合结果（不持久化）
    # ═══════════════════════════════════════════════════════════════

    async def _finalize_node(self, state: ResourceGenState) -> dict:
        content_blocks = state.get("content_blocks", [])
        questions = state.get("questions", [])
        topic = state.get("topic", "")

        self._emit(state, stage_start("finalize", "正在汇总生成结果..."))

        response = (
            f"已为您生成「{topic}」的学习资源，"
            f"共 {len(content_blocks)} 个内容块 + {len(questions)} 道练习题。"
        )

        self._emit(state, stage_end("finalize",
            f"汇总完成，共 {len(content_blocks)} 个内容块 + {len(questions)} 道练习题"))

        return {
            "resource_ids": [],
            "response": response,
        }
