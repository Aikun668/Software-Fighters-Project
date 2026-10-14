"""聊天域任务分发与事件编排（P3-B3a 由 `ResultAgent` 改名而来）。

职责：把 `ExecutionPlan` 里的 `tasks` 逐条派给对应 Center（`_center_for` 映射表），
并把各 Center 的结果装配成 SSE 事件流 + 终局 `done` 载荷。

【命名澄清】原名 `ResultAgent`（名不副实：它是**调度器**，不是"结果整理 Agent"）。
  - 作用域：**只服务聊天域** —— 生产代码中唯一引用者是 `ChatCenter`
    （`app/centers/chat_center.py`），由契约 `ST-D02` 锁定；
  - GUIDE P2 的「不再承担跨业务域的默认总调度」在**调用拓扑上已达成**；
  - 仍保留的职责（SSE 事件拼装 / 正文合成 `_ensure_user_visible_response`）是否迁移，
    见 `P3-B3状态与职责收敛实施方案.md` 的 P3-B3b（**行为变更轮**，未做）；
  - 注：`tests/test_chat_center_api_delegation.py` 锁的是「API 层不得出现本符号」，
    属**分层断言**，并非对本类名的锁定。
"""

import asyncio
import logging
from typing import Any, AsyncGenerator

from app.agents.adjustment_agent import AdjustmentAgent
from app.agents.decompose_agent import DecomposeAgent
from app.agents.goal_agent import GoalAgent
from app.agents.layered_explain_agent import LayeredExplainAgent
from app.agents.schedule_agent import ScheduleAgent
from app.centers.auto_center import AutoCenter
from app.centers.exercise_center import ExerciseCenter
from app.centers.plan_center import PlanCenter
from app.centers.resource_center import ResourceCenter
from app.centers.schemas import (
    AggregatedResult,
    CenterResult,
    CenterTask,
    ExecutionPlan,
)
from app.agents.base_agent import current_emitter
from app.centers.visualization_center import VisualizationCenter
from app.events.graph_stream import graph_stream_enabled
from app.events.stream import (
    MessageDeltaCollector,
    ProgressEvent,
    ProgressEventType,
    StreamEmitter,
)
from app.events.types import (
    StreamEvent,
    StreamEventType,
    center_end_event,
    center_start_event,
    done_event,
    error_event,
    inquiry_event,
)
from app.services.capability_map import ON_TOKEN_CENTERS


def _token_event(chunk: str) -> StreamEvent:
    """逐字 token 事件：前端 parseSSEStream 已有 case 'token' 分支直接消费。
    不用 content_event 因为前端 content 分支会读 response/content 字段
    重复追加完整文本。"""
    return StreamEvent(
        type=StreamEventType.TOKEN,
        data={"content": chunk},
    )


def _finalize_event(payload: dict, *, streamed: bool = True) -> StreamEvent:
    """收尾事件（本中心的最终产物）。

    `streamed` 决定 `partial` 标记 —— 这个标记的语义是
    「**正文已通过 token 逐块送过，本帧只是结构化收尾，勿重复渲染**」：

    - ``streamed=True``：本中心确实逐字发过 token（如 auto / exercise）
      → 带 ``partial=True``，前端跳过文本追加，避免重复。
    - ``streamed=False``：本中心**不产生 token 流**（如 plan / resource）
      → **不带** ``partial``，因为此帧是该轮**唯一**正文载体，
        前端必须渲染；打上 ``partial`` 会让唯一正文被丢弃。

    历史缺陷：本函数曾**无条件**打 ``partial=True``，导致"正文只在收尾帧
    下发"的中心被前端整轮跳过，表现为「后端没有返回任何内容」。
    """
    data = {**payload, "partial": True} if streamed else payload
    return StreamEvent(
        type=StreamEventType.CONTENT,
        data=data,
    )


def _progress_event(node_event: ProgressEvent, phase: str) -> StreamEvent:
    """内部**图节点**事件 → 线上 `progress` 帧（阶段 D：把执行过程变成前端可见）。

    - `stage` 带**节点名**（内部名，如 `extract`）；`message` 是**占位文案** ——
      「节点/事件 → 用户可见文案」映射表本轮**不做**，前端先按占位展示。
    - 载荷只带 `node` / `phase`（`started` | `completed`），**不掺正文**，
      以免与既有 `token` 帧重复渲染（契约 `PG-A04`）。
    """
    node = str(node_event.data.get("node", ""))
    text = f"正在执行 {node}" if phase == "started" else f"{node} 已完成"
    return StreamEvent(
        type=StreamEventType.PROGRESS,
        stage=node,
        message=text,
        data={"node": node, "phase": phase},
    )


logger = logging.getLogger(__name__)


class ChatTaskDispatcher:
    CENTER_DELAY_SECONDS = 0.0

    # 需要逐字 token 回调的 mode（其余 Center 的 execute 不接 on_token）。
    # 与 `_center_for` 一样，把 mode 字面量集中为**数据**，不散落在 if 比较里。
    # - auto：TutorAgent 经 llm.chat_stream 逐字吐正文
    # - exercise：ExerciseAgent 逐题下发给题面、review 阶段下发答案
    _ON_TOKEN_MODES = ON_TOKEN_CENTERS

    def __init__(
        self,
        auto_center: AutoCenter | None = None,
        plan_center: PlanCenter | None = None,
        resource_center: ResourceCenter | None = None,
        exercise_center: ExerciseCenter | None = None,
        visualization_center: VisualizationCenter | None = None,
        decompose_agent: DecomposeAgent | None = None,
        layered_explain_agent: LayeredExplainAgent | None = None,
        goal_agent: GoalAgent | None = None,
        schedule_agent: ScheduleAgent | None = None,
        adjustment_agent: AdjustmentAgent | None = None,
        use_mock_llm: bool = False,
    ):
        # AutoCenter 的各 Agent 由其内部惰性默认构造；
        # decompose/layered_explain 仅 PlanCenter/AutoCenter 显式注入时使用
        # P0-B：默认构造的 Center 继承本旗标，保证裸构造 dispatcher 也能离线跑
        self.auto_center = auto_center or AutoCenter(use_mock_llm=use_mock_llm)
        self.plan_center = plan_center or PlanCenter(
            goal_agent=goal_agent,
            decompose_agent=decompose_agent,
            schedule_agent=schedule_agent,
            adjustment_agent=adjustment_agent,
            use_mock_llm=use_mock_llm,
        )
        self.resource_center = resource_center or ResourceCenter(use_mock_llm=use_mock_llm)
        self.exercise_center = exercise_center or ExerciseCenter(use_mock_llm=use_mock_llm)
        self.visualization_center = visualization_center or VisualizationCenter(
            use_mock_llm=use_mock_llm
        )

    async def execute(
        self,
        plan: ExecutionPlan,
        event_queue: asyncio.Queue | None = None,
        emitter: StreamEmitter | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        if plan.tasks and plan.tasks[0].mode == "inquiry":
            task = plan.tasks[0]
            question = task.params.get("question", "你想了解什么？")
            yield inquiry_event(question)
            yield done_event({
                "type": "inquiry",
                "question": question,
                "is_clear": False,
            })
            return

        aggregated = AggregatedResult()
        total = len(plan.tasks)

        # ── P3-E（流式阶段 B）：本 run 的统一事件源 + 对账 Collector。
        # 事件源只有一个（下面的 token pump），消费者已有两个：
        #   ① token_queue → SSE（既有通路，**逐字不变**）
        #   ② MessageDeltaCollector → 完整文本对账（只记录，不进 SSE 载荷）
        run_emitter = emitter or StreamEmitter()
        delta_collector = MessageDeltaCollector()
        run_emitter.subscribe(delta_collector)

        # ── 阶段 D：把内部**图节点**事件搬到线上（只**新增** progress 帧，既有帧不变）。
        # 订阅者必须是同步可调用对象，故只做 `put_nowait`；由主循环按事件顺序吐出。
        progress_queue: asyncio.Queue = asyncio.Queue()

        def _forward_progress(event: ProgressEvent) -> None:
            if event.type is ProgressEventType.NODE_STARTED:
                progress_queue.put_nowait(_progress_event(event, "started"))
            elif event.type is ProgressEventType.NODE_COMPLETED:
                progress_queue.put_nowait(_progress_event(event, "completed"))

        run_emitter.subscribe(_forward_progress)
        run_emitter.emit(ProgressEventType.RUN_STARTED, tasks=total)

        for idx, task in enumerate(plan.tasks):
            progress = round((idx / total) * 100) / 100 if total else 0.0
            yield center_start_event(
                center=task.mode,
                message=f"开始执行 {task.mode} 中心...",
                sequence=idx,
            )

            # ── B1-4：边等 center 完整结果边把 token 流式 yield 到 SSE。
            # 产生 token 的是 `_ON_TOKEN_MODES`（auto / exercise）：
            #   - auto：TutorAgent 经 `llm.chat_stream` 逐字吐正文；
            #   - exercise：ExerciseAgent 逐题吐题面、review 阶段吐答案。
            # 其余 center 忽略 on_token，queue 始终为空，
            # 主循环 0.05s 后拿到 result（其正文只在收尾帧下发）。
            #
            # 用 asyncio.Queue + 异步 on_token：
            #   - put 是 await 的（流速自然匹配消费速度，逐字）
            #   - get 是 await 的（主循环一边 yield 一边等 chunk）
            token_queue: asyncio.Queue = asyncio.Queue()
            # 本轮是否真的对外发过 token —— 决定收尾帧要不要打 partial 标记
            emitted_tokens = False

            run_emitter.emit(
                ProgressEventType.CENTER_STARTED, center=task.mode, sequence=idx,
            )

            async def _on_token(chunk: str) -> None:
                # 「一次生成、多方消费」：先发 message.delta 事件（广播给 Collector 等），
                # 再进既有 SSE 通路。chunk 本体不做任何加工 → SSE 字节逐字不变。
                await run_emitter.on_token(chunk)
                await token_queue.put(chunk)

            # 阶段 C：把本 run 的事件源注入协程上下文（create_task 会复制上下文），
            # 于是 Agent 内部的 LangGraph 节点事件也会汇入同一条事件流。
            # `AI_SERVICE_GRAPH_STREAM=0` 时注入 None → Agent 退回 `ainvoke` 纯路径。
            emitter_ctx_token = current_emitter.set(
                run_emitter if graph_stream_enabled() else None,
            )
            result_task = asyncio.create_task(
                self._execute_task(task, on_token=_on_token)
            )

            try:
                while not result_task.done():
                    try:
                        chunk = await asyncio.wait_for(
                            token_queue.get(), timeout=0.05
                        )
                    except asyncio.TimeoutError:
                        chunk = None

                    # 进度帧先于紧随其后的 token 吐出，保持事件的时间顺序
                    while not progress_queue.empty():
                        yield progress_queue.get_nowait()

                    if chunk is not None:
                        emitted_tokens = True
                        yield _token_event(chunk)

                result = await result_task
                # 排空残留 chunk（generate_once 完成时旁路可能还有几个
                # chunk 没被消费），避免和最终的完整 content 重复。
                while not token_queue.empty():
                    try:
                        chunk = token_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    emitted_tokens = True
                    yield _token_event(chunk)

                # 任务结束后补吐剩余进度帧（全部早于 center_end / done）
                while not progress_queue.empty():
                    yield progress_queue.get_nowait()

                aggregated.results.append(result)
            finally:
                current_emitter.reset(emitter_ctx_token)
                if not result_task.done():
                    result_task.cancel()
                    try:
                        await result_task
                    except (asyncio.CancelledError, Exception):
                        pass

            yield center_end_event(
                center=task.mode,
                message=f"{task.mode} 中心执行完成",
                sequence=idx,
            )

            run_emitter.emit(
                ProgressEventType.CENTER_COMPLETED,
                center=task.mode,
                sequence=idx,
                error=bool(result.error),
            )

            # 出错时不发 finalize（partial 对错误事件无意义，走 error_event）
            if result.error:
                yield error_event(stage=result.mode, message=result.error)
            else:
                # ── B1 终态事件：本中心**确实发过 token** 时带 partial=True，
                # 前端据此跳过文本追加（防重复）；未发过 token 的中心
                # 不带该标记，因为此帧是唯一正文载体，必须被渲染。
                yield _finalize_event(
                    self._serialize_final_payload(result, progress),
                    streamed=emitted_tokens,
                )

            if result.profile_delta:
                aggregated.profile_delta.update(result.profile_delta)

            if self.CENTER_DELAY_SECONDS > 0 and idx < total - 1:
                await asyncio.sleep(self.CENTER_DELAY_SECONDS)

        summary = self._build_summary(aggregated)
        aggregated.summary = summary
        aggregated.next_steps = self._build_next_steps(aggregated)

        # 对账（指导文档 §6-3）：前端逐字收到的文本 vs 后台收集的完整文本
        run_emitter.emit(
            ProgressEventType.RUN_COMPLETED,
            tasks=total,
            deltas=delta_collector.delta_count,
            chars=len(delta_collector.text),
        )
        logger.info(
            "stream run %s: %d task(s), %d delta(s), %d char(s)",
            run_emitter.run_id, total,
            delta_collector.delta_count, len(delta_collector.text),
        )

        yield done_event({
            "type": "done",
            "summary": summary,
            "next_steps": aggregated.next_steps,
            "profile_delta": aggregated.profile_delta,
            "results": [self._serialize_result(r) for r in aggregated.results],
        })

    def _center_for(self, mode: str):
        """`mode` → Center 显式映射表（未知 mode 返回 None）。

        P3-B3a：取代原先的 `if task.mode == ...` if-链 —— 新增业务域只需在此表加一行。
        """
        return {
            "auto": self.auto_center,
            "plan": self.plan_center,
            "resource": self.resource_center,
            "exercise": self.exercise_center,
            "visualization": self.visualization_center,
        }.get(mode)

    async def _execute_task(self, task: CenterTask, on_token=None) -> CenterResult:
        try:
            center = self._center_for(task.mode)
            if center is None:
                return CenterResult(
                    mode=task.mode,
                    intent=task.intent,
                    event_type="error",
                    error=f"未知 center: {task.mode}",
                    sequence=task.sequence,
                )
            if task.mode in self._ON_TOKEN_MODES:
                # 只有对话底座需要逐字 token 回调；其余 Center 不收 on_token
                return await center.execute(task, on_token=on_token)
            return await center.execute(task)
        except Exception as e:
            logger.error(f"ChatTaskDispatcher execute task failed: {e}")
            return CenterResult(
                mode=task.mode,
                intent=task.intent,
                event_type="error",
                error="处理失败",
                sequence=task.sequence,
            )

    def _result_to_event(self, result: CenterResult, progress: float) -> StreamEvent:
        if result.error:
            return error_event(
                stage=result.mode,
                message=result.error,
            )
        return StreamEvent(
            type=self._map_event_type(result.event_type),
            stage=result.mode,
            message=f"{result.agent} 输出",
            progress=progress,
            data=self._ensure_user_visible_response(result),
        )

    def _serialize_final_payload(
        self, result: CenterResult, progress: float
    ) -> dict:
        """B1 终态：与 _result_to_event 共享 payload 抽取逻辑，但只返回 dict
        （让 _finalize_event 包装成 partial=True 事件）。出错时返回空 dict，
        改走 error_event（partial 对错误事件无意义）。"""
        if result.error:
            return {}
        return {
            "stage": result.mode,
            "message": f"{result.agent} 输出",
            "progress": progress,
            **self._ensure_user_visible_response(result),
        }

    @staticmethod
    def _ensure_user_visible_response(result: CenterResult) -> dict:
        """统一 content 合同（Task 11 评审回归项）：前端与 internal_api 的正文
        只从 payload 的 response/content 键提取。中心产物 payload 若两者皆无，
        优先取真实产物文本（solve 的 solution），仍无才合成用户可读摘要
        （cap-01/05/06）。合不出摘要时保持 payload 原样，空正文由
        internal_api 的终态合同转成 error，而不是伪造 content。"""
        payload = result.payload if isinstance(result.payload, dict) else {}
        if payload.get("response") or payload.get("content"):
            return payload
        solution = payload.get("solution")
        if isinstance(solution, str) and solution.strip():
            return {**payload, "response": solution, "content": solution}
        summary = ChatTaskDispatcher._summarize_product(result.mode, payload)
        if not summary:
            return payload
        return {**payload, "response": summary, "content": summary}

    @staticmethod
    def _summarize_product(mode: str, payload: dict) -> str:
        title = str(payload.get("title") or payload.get("topic") or "").strip()
        quoted = f"「{title}」" if title else ""
        if mode == "plan":
            steps = payload.get("steps") or []
            total = payload.get("total_steps") or len(steps)
            text = f"已为你生成{quoted}学习计划，共 {total} 步"
            names = []
            for step in steps[:3]:
                if isinstance(step, dict):
                    name = step.get("title") or step.get("topic") or step.get("name")
                    if name:
                        names.append(str(name))
            if names:
                text += "：" + "；".join(names)
            days = payload.get("estimated_days")
            if days:
                text += f"，预计 {days} 天完成"
            return text + "。"
        if mode == "visualization":
            blocks = payload.get("blocks") or []
            return f"已为你生成{quoted}的可视化图解，共 {len(blocks)} 个内容块。"
        if mode == "exercise":
            count = payload.get("count") or payload.get("total")
            return f"已为你生成{quoted}的 {count} 道练习题。" if count else f"已为你生成{quoted}练习题。"
        if mode == "resource":
            return f"已为你生成{quoted}的学习资源。"
        # 无可描述产物（如 auto 中心空回答）时返回空串：由上层终态合同
        # 补 error，而不是伪造「已完成xx处理。」
        return ""

    def _map_event_type(self, event_type: str) -> StreamEventType:
        mapping = {
            "content": StreamEventType.CONTENT,
            "plan": StreamEventType.CONTENT,
            "resource": StreamEventType.CONTENT,
            "exercise": StreamEventType.CONTENT,
            "visualization": StreamEventType.CONTENT,
            "error": StreamEventType.ERROR,
            "inquiry": StreamEventType.INQUIRY,
        }
        return mapping.get(event_type, StreamEventType.CONTENT)

    def _build_summary(self, aggregated: AggregatedResult) -> str:
        if not aggregated.results:
            return "已完成处理。"
        parts = []
        for r in aggregated.results:
            if r.error:
                parts.append(f"{r.mode} 执行出现错误")
            else:
                parts.append(f"{r.mode} 已完成")
        return "；".join(parts) + "。"

    def _build_next_steps(self, aggregated: AggregatedResult) -> list[str]:
        steps = []
        intents = [r.intent for r in aggregated.results if not r.error]
        if "learning_path" in intents and "exercise_gen" not in intents:
            steps.append("可以尝试生成配套练习题巩固路径内容")
        if "exercise_gen" in intents and "learning_path" not in intents:
            steps.append("可以规划系统学习路径")
        if "resource_gen" in intents:
            steps.append("可以导出为 PPT/PDF 便于复习")
        return steps

    def _serialize_result(self, result: CenterResult) -> dict[str, Any]:
        return {
            "mode": result.mode,
            "intent": result.intent,
            "event_type": result.event_type,
            "agent": result.agent,
            "sequence": result.sequence,
            "error": result.error,
            "payload_keys": list(result.payload.keys()),
        }
