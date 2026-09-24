"""中心结果聚合与跨业务域任务调度。

【命名澄清】名字叫 `ResultAgent`，实际职责是**跨业务域总调度 + SSE 终态编排**
  （`_execute_task` 分发到 auto / plan / resource / exercise / visualization）：
  - GUIDE P2 要求其「不再承担跨业务域的默认总调度」，**该项尚未收敛**（P2 遗留，独立轮）
  - 注：`tests/test_chat_center_api_delegation.py` 锁的是「API 层不得出现本符号」，
    属**分层断言**，并非对本类名的锁定
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
from app.centers.visualization_center import VisualizationCenter
from app.events.types import (
    StreamEvent,
    StreamEventType,
    center_end_event,
    center_start_event,
    done_event,
    error_event,
    inquiry_event,
)


def _token_event(chunk: str) -> StreamEvent:
    """逐字 token 事件：前端 parseSSEStream 已有 case 'token' 分支直接消费。
    不用 content_event 因为前端 content 分支会读 response/content 字段
    重复追加完整文本。"""
    return StreamEvent(
        type=StreamEventType.TOKEN,
        data={"content": chunk},
    )


def _finalize_event(payload: dict) -> StreamEvent:
    """最终事件：带 partial=True 标记，前端 case 'content' 据此跳过文本追加
    （token 流阶段已经把字送完了）。payload 仍保留 blocks 等结构化信息，
    供后续渲染使用。"""
    return StreamEvent(
        type=StreamEventType.CONTENT,
        data={**payload, "partial": True},
    )


logger = logging.getLogger(__name__)


class ResultAgent:
    CENTER_DELAY_SECONDS = 0.0

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
    ):
        # AutoCenter 的各 Agent 由其内部惰性默认构造；
        # decompose/layered_explain 仅 PlanCenter/AutoCenter 显式注入时使用
        self.auto_center = auto_center or AutoCenter()
        self.plan_center = plan_center or PlanCenter(
            goal_agent=goal_agent,
            decompose_agent=decompose_agent,
            schedule_agent=schedule_agent,
            adjustment_agent=adjustment_agent,
        )
        self.resource_center = resource_center or ResourceCenter()
        self.exercise_center = exercise_center or ExerciseCenter()
        self.visualization_center = visualization_center or VisualizationCenter()

    async def execute(
        self,
        plan: ExecutionPlan,
        event_queue: asyncio.Queue | None = None,
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

        for idx, task in enumerate(plan.tasks):
            progress = round((idx / total) * 100) / 100 if total else 0.0
            yield center_start_event(
                center=task.mode,
                message=f"开始执行 {task.mode} 中心...",
                sequence=idx,
            )

            # ── B1-4：边等 center 完整结果边把 token 流式 yield 到 SSE。
            # 只有 auto/tutor 路径会真正产生 token（auto_center 内部
            # TutorAgent 在 generate_once 内 await on_token(chunk)，
            # 必须 await 才能保证逐字流出）；其他 center 忽略 on_token，
            # queue 始终为空，主循环 0.05s 后拿到 result。
            #
            # 用 asyncio.Queue + 异步 on_token：
            #   - put 是 await 的（流速自然匹配消费速度，逐字）
            #   - get 是 await 的（主循环一边 yield 一边等 chunk）
            token_queue: asyncio.Queue = asyncio.Queue()

            async def _on_token(chunk: str) -> None:
                await token_queue.put(chunk)

            result_task = asyncio.create_task(
                self._execute_task(task, on_token=_on_token)
            )

            try:
                while not result_task.done():
                    try:
                        chunk = await asyncio.wait_for(
                            token_queue.get(), timeout=0.05
                        )
                        yield _token_event(chunk)
                    except asyncio.TimeoutError:
                        continue

                result = await result_task
                # 排空残留 chunk（generate_once 完成时旁路可能还有几个
                # chunk 没被消费），避免和最终的完整 content 重复。
                while not token_queue.empty():
                    try:
                        chunk = token_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    yield _token_event(chunk)

                aggregated.results.append(result)
            finally:
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

            # 出错时不发 finalize（partial 对错误事件无意义，走 error_event）
            if result.error:
                yield error_event(stage=result.mode, message=result.error)
            else:
                # ── B1 终态事件：partial=True，前端不再重复追加（token 流已逐字送完）
                yield _finalize_event(self._serialize_final_payload(result, progress))

            if result.profile_delta:
                aggregated.profile_delta.update(result.profile_delta)

            if self.CENTER_DELAY_SECONDS > 0 and idx < total - 1:
                await asyncio.sleep(self.CENTER_DELAY_SECONDS)

        summary = self._build_summary(aggregated)
        aggregated.summary = summary
        aggregated.next_steps = self._build_next_steps(aggregated)

        yield done_event({
            "type": "done",
            "summary": summary,
            "next_steps": aggregated.next_steps,
            "profile_delta": aggregated.profile_delta,
            "results": [self._serialize_result(r) for r in aggregated.results],
        })

    async def _execute_task(self, task: CenterTask, on_token=None) -> CenterResult:
        try:
            if task.mode == "auto":
                return await self.auto_center.execute(task, on_token=on_token)
            if task.mode == "plan":
                return await self.plan_center.execute(task)
            if task.mode == "resource":
                return await self.resource_center.execute(task)
            if task.mode == "exercise":
                return await self.exercise_center.execute(task)
            if task.mode == "visualization":
                return await self.visualization_center.execute(task)
            return CenterResult(
                mode=task.mode,
                intent=task.intent,
                event_type="error",
                error=f"未知 center: {task.mode}",
                sequence=task.sequence,
            )
        except Exception as e:
            logger.error(f"ResultAgent execute task failed: {e}")
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
        summary = ResultAgent._summarize_product(result.mode, payload)
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
