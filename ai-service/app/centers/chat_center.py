import asyncio
import logging
import time
from typing import Any, AsyncIterator

from app.agents.adjustment_agent import AdjustmentAgent
from app.agents.decompose_agent import DecomposeAgent
from app.agents.diagnose_agent import DiagnoseAgent
from app.agents.exercise_agent import ExerciseAgent
from app.agents.goal_agent import GoalAgent
from app.agents.profile_agent import ProfileAgent
from app.agents.schedule_agent import ScheduleAgent
from app.agents.content_agent import ContentAgent
from app.centers.auto_center import AutoCenter
from app.centers.exercise_center import ExerciseCenter
from app.centers.plan_center import PlanCenter
from app.centers.resource_center import ResourceCenter
from app.centers.chat_task_dispatcher import ChatTaskDispatcher
from app.centers.router_agent import RouterAgent
from app.centers.schemas import CenterTask, ExecutionPlan
from app.centers.visualization_center import VisualizationCenter
from app.events.types import (
    StreamEvent,
    StreamEventType,
    done_event,
    error_event,
    knowledge_candidates_event,
    recommendation_event,
)
from app.services.capability_gate import CapabilityGate, CapabilityKind
from app.services.capability_map import KIND_TO_CENTER
from app.services.intent_extractor import IntentExtractor
from app.services.routing_audit import (
    build_routing_record,
    emit_routing_record,
    new_trace_id,
)
from app.services.llm_service import (
    PROFILE_EXERCISE,
    PROFILE_STUDENT,
)

logger = logging.getLogger(__name__)


class ChatCenter:
    # 推荐抽取（LLM 调用）的超时预算，防止 done 被阻塞。Task 2 收敛到
    # 一次抽取,派生两个事件（recommendation_event + knowledge_candidates_event）;
    # 实例属性 _recommendation_timeout_sec 可被测试或装配层覆盖。
    RECOMMENDATION_TIMEOUT_SEC: float = 10.0

    def __init__(
        self,
        router_agent: RouterAgent | None = None,
        dispatcher: ChatTaskDispatcher | None = None,
        capability_gate: CapabilityGate | None = None,
        use_mock_llm: bool = False,
    ):
        self.router_agent = router_agent
        self.dispatcher = dispatcher
        self.capability_gate = capability_gate
        # P0-B：默认 dispatcher 路径要把旗标透传给 8 Agent + 5 Center。
        # 不透传时，BaseAgent 的默认 `use_mock_llm=False` 会**显式**阻断环境跟随，
        # 无 Key 环境在构造期抛 ValueError（见 tests/test_mock_llm_switch_contract.py）。
        self.use_mock_llm = use_mock_llm

    def _get_router(self) -> RouterAgent:
        if self.router_agent is None:
            self.router_agent = RouterAgent(intent_extractor=IntentExtractor())
        return self.router_agent

    def _get_gate(self) -> CapabilityGate:
        if self.capability_gate is None:
            self.capability_gate = CapabilityGate()
        return self.capability_gate

    def _get_dispatcher(self) -> ChatTaskDispatcher:
        if self.dispatcher is None:
            mock = self.use_mock_llm
            decompose = DecomposeAgent(use_mock_llm=mock)
            goal = GoalAgent(use_mock_llm=mock)
            schedule = ScheduleAgent(use_mock_llm=mock)
            adjustment = AdjustmentAgent(use_mock_llm=mock)
            diagnose = DiagnoseAgent(use_mock_llm=mock)
            profile = ProfileAgent(use_mock_llm=mock)
            exercise = ExerciseAgent(model_profile=PROFILE_EXERCISE, use_mock_llm=mock)
            content = ContentAgent(use_mock_llm=mock)

            self.dispatcher = ChatTaskDispatcher(
                auto_center=AutoCenter(
                    diagnose_agent=diagnose,
                    profile_agent=profile,
                    use_mock_llm=mock,
                ),
                plan_center=PlanCenter(
                    goal_agent=goal,
                    decompose_agent=decompose,
                    schedule_agent=schedule,
                    adjustment_agent=adjustment,
                    use_mock_llm=mock,
                ),
                resource_center=ResourceCenter(
                    content_agent=content,
                    use_mock_llm=mock,
                ),
                exercise_center=ExerciseCenter(
                    exercise_agent=exercise,
                    use_mock_llm=mock,
                ),
                visualization_center=VisualizationCenter(use_mock_llm=mock),
                use_mock_llm=mock,
            )
        return self.dispatcher

    @staticmethod
    def _audit_context(message: str, context: dict | None) -> dict:
        """从请求上下文提取观测字段（只取元数据，不含消息正文）。"""
        context = context or {}
        msgs = list(context.get("messages") or [])
        turn_count = len(msgs)
        # 末尾恰好是本次当前消息时（internal_api 传入 history+[user_msg]），不计入历史
        if (
            msgs
            and msgs[-1].get("role") == "user"
            and msgs[-1].get("content") == message
        ):
            turn_count -= 1
        return {
            "trace_id": context.get("trace_id") or new_trace_id(),
            "conversation_id": context.get("conversation_id"),
            "context_turn_count": turn_count,
        }

    async def route(
        self,
        message: str,
        mode: str = "auto",
        student_profile: dict | None = None,
        context: dict | None = None,
        max_intents: int = 3,
    ) -> ExecutionPlan:
        if not message.strip():
            # 空输入不进能力判定，交由路由层给出 inquiry 追问
            return await self._get_router().route(
                message=message,
                mode=mode,
                student_profile=student_profile,
                context=context,
                max_intents=max_intents,
            )

        # 一级判定：CapabilityGate。默认 NORMAL_CHAT 直达 TutorAgent，
        # 只有明确能力请求才进入 RouterAgent → ExecutionPlan → ChatTaskDispatcher。
        decision = self._get_gate().decide(
            message=message,
            mode=mode,
            student_profile=student_profile,
            context=context,
        )
        audit_meta = self._audit_context(message, context)

        if decision.kind is CapabilityKind.NORMAL_CHAT:
            context = context or {}
            task = CenterTask(
                mode="auto",
                intent="tutor_question",
                input=message,
                params={"question": message.strip()},
                context={
                    **context,
                    "student_profile": student_profile or {},
                    "capability_route": decision.kind.value,
                    "capability_reason": decision.reason,
                },
                confidence=decision.confidence,
            )
            return ExecutionPlan(
                tasks=[task],
                is_clear=True,
                intent_meta={
                    "raw_message": message,
                    "strategy": "capability_gate",
                    "route": decision.kind.value,
                    "route_reason": decision.reason,
                    **audit_meta,
                },
            )

        plan = await self._get_router().route(
            message=message,
            mode=mode,
            student_profile=student_profile,
            context=context,
            max_intents=max_intents,
        )
        # gate 判定了能力，二级路由必须进入对应中心，不得回落 tutor（Task 11 回归项）
        expected_center = KIND_TO_CENTER.get(decision.kind.value)
        if expected_center and not any(t.mode == expected_center for t in plan.tasks):
            # 二级关键词路由未命中 gate 判定的中心（回落 tutor）时，
            # 以显式 mode 直建对应中心的单任务计划，保证 gate 判定权威
            plan = await self._get_router().route(
                message=message,
                mode=decision.kind.value.lower(),
                student_profile=student_profile,
                context=context,
                max_intents=max_intents,
            )
        # 能力路径同样带观测元数据，供 execute 边界产出审计日志
        plan.intent_meta.update({
            "route": decision.kind.value,
            "route_reason": decision.reason,
            **audit_meta,
        })
        return plan

    async def execute(self, plan: ExecutionPlan):
        meta = plan.intent_meta or {}
        audit_route = meta.get("route")
        result = self._get_dispatcher()

        started = time.perf_counter()
        terminal: str | None = None
        try:
            async for event in result.execute(plan):
                if event.type in (
                    StreamEventType.DONE,
                    StreamEventType.ERROR,
                    StreamEventType.INQUIRY,
                ):
                    terminal = event.type.value
                yield event
        except Exception:
            terminal = "error"
            raise
        finally:
            if audit_route:
                emit_routing_record(build_routing_record(
                    trace_id=meta.get("trace_id") or new_trace_id(),
                    conversation_id=meta.get("conversation_id"),
                    route=audit_route,
                    route_reason=meta.get("route_reason", ""),
                    context_turn_count=meta.get("context_turn_count", 0),
                    model_latency_ms=(time.perf_counter() - started) * 1000,
                    sse_terminal_event=terminal,
                ))

    @staticmethod
    def _done_payload_has_content(done_data: Any) -> bool:
        """done 载荷是否携带"无需 token 流"的合法产物。

        资源 / 计划 / 练习 / 路径 / 画像模式正文不走 token 流,而是随 done 载荷下发;
        追问（inquiry）以问题文本作为本轮产出,也不算"空正文失败"。
        summary/results 等是描述性元数据,不参与判定。
        """
        if not isinstance(done_data, dict):
            return False
        if done_data.get("is_clear") is False or done_data.get("type") == "inquiry":
            return True
        for key in (
            "content_blocks",
            "questions",
            "plan",
            "_path_steps",
            "steps",
            "profile_delta",
        ):
            value = done_data.get(key)
            if isinstance(value, list) and value:
                return True
            if isinstance(value, dict) and value:
                return True
        for key in ("response", "content", "solution"):
            value = done_data.get(key)
            if isinstance(value, str) and value.strip():
                return True
        return False

    async def stream_chat(
        self,
        *,
        message: str,
        history: list[dict] | None = None,
        mode: str = "auto",
        student_profile: dict | None = None,
        user_id: int,
        conversation_id: str | None = None,
        style: str = "standard",
        images: list[str] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """统一聊天唯一业务入口（Task 2 收口）。

        责任：
        1. route() → ExecutionPlan
        2. ChatTaskDispatcher.execute(plan) → 业务事件流（含内部 done）
        3. 收集 assistant_content（token / content / partial payload）
        4. 在最终 done 前调一次 extract_knowledge_nodes（超时预算内）
           ├─ primary[0] → recommendation_event
           └─ primary/related/broad → knowledge_candidates_event
        5. 多 done 收敛为唯一 done（失败补 error,缺 done 补 done）
        6. 消费端取消时取消 ChatTaskDispatcher 任务并回收

        images: 用户上传的图片（data URI / http URL），随 context 下发；
        仅 tutor 答疑链路消费（见 auto_center / tutor_agent）。
        """
        messages = list(history or []) + [{"role": "user", "content": message}]
        context = {
            "messages": messages,
            "style": style,
            "images": list(images or []),
            "user_id": user_id,
            "conversation_id": conversation_id,
        }
        plan = await self.route(
            message=message,
            mode=mode,
            student_profile=student_profile,
            context=context,
        )

        result = self._get_dispatcher()
        extract_fn = getattr(self, "_extract_knowledge_nodes", None)
        if extract_fn is None:
            from app.services.knowledge_extraction import (
                extract_knowledge_nodes as _default_extract,
            )
            extract_fn = _default_extract
        timeout = (
            getattr(self, "_recommendation_timeout_sec", None)
            or self.RECOMMENDATION_TIMEOUT_SEC
        )

        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        state: dict[str, Any] = {
            "saw_done": False,
            "final_data": None,
            "assistant_content": "",
            "saw_error": False,
        }

        async def _producer() -> None:
            try:
                async for event in result.execute(plan):
                    # 收集正文（token + content 都视作正文流）
                    if (
                        event.type is StreamEventType.TOKEN
                        and isinstance(event.data, dict)
                    ):
                        chunk = event.data.get("content", "")
                        if isinstance(chunk, str):
                            state["assistant_content"] += chunk
                    elif event.type is StreamEventType.CONTENT and event.data:
                        if isinstance(event.data, str):
                            state["assistant_content"] += event.data
                        elif isinstance(event.data, dict):
                            chunk = (
                                event.data.get("response")
                                or event.data.get("content")
                                or ""
                            )
                            if isinstance(chunk, str):
                                state["assistant_content"] += chunk
                    if event.type is StreamEventType.ERROR:
                        state["saw_error"] = True

                    # 第一个 done：在它之前插入推荐事件，再 yield done。
                    if event.type is StreamEventType.DONE:
                        if state["saw_done"]:
                            continue
                        state["saw_done"] = True
                        state["final_data"] = event.data

                        # 终态合同：done 载荷带 error 字段 → 先发可读 error；
                        # 空正文且 done 载荷无合法产物且未见 error → 补发空正文 error。
                        done_error = (
                            event.data.get("error")
                            if isinstance(event.data, dict)
                            else None
                        )
                        if isinstance(done_error, str) and done_error.strip():
                            await queue.put(
                                error_event(stage="chat", message=done_error)
                            )
                        elif (
                            not state["saw_error"]
                            and not state["assistant_content"].strip()
                            and not self._done_payload_has_content(event.data)
                        ):
                            await queue.put(
                                error_event(
                                    stage="chat",
                                    message="模型未返回有效内容，请重试",
                                )
                            )

                        if state["assistant_content"].strip():
                            course_id = ""
                            if plan.tasks:
                                course_id = str(
                                    plan.tasks[0].context.get("course_id", "")
                                )
                            extracted: Any = None
                            try:
                                extracted = await asyncio.wait_for(
                                    extract_fn(
                                        course_id=course_id,
                                        user_message=message,
                                        assistant_reply=state["assistant_content"][:2000],
                                    ),
                                    timeout=timeout,
                                )
                            except asyncio.TimeoutError:
                                logger.warning(
                                    "Recommendation extraction timed out after %.1fs",
                                    timeout,
                                )
                            except Exception as exc:  # noqa: BLE001
                                logger.warning(
                                    "Recommendation extraction failed: %s", exc
                                )
                            if isinstance(extracted, dict):
                                primary = extracted.get("primary") or []
                                related = extracted.get("related") or []
                                broad = extracted.get("broad") or []
                                if primary and isinstance(primary[0], dict):
                                    node = primary[0]
                                    await queue.put(
                                        recommendation_event(
                                            knowledge_node_id=str(
                                                node.get("id", "")
                                            ),
                                            node_name=str(node.get("name", "")),
                                        )
                                    )
                                if primary or related or broad:
                                    await queue.put(
                                        knowledge_candidates_event(
                                            {
                                                "primary": primary,
                                                "related": related,
                                                "broad": broad,
                                            }
                                        )
                                    )
                        await queue.put(event)
                        return

                    await queue.put(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception("Chat pipeline failed: %s", exc)
                state["saw_error"] = True
                await queue.put(
                    error_event(
                        stage="chat",
                        message=str(exc) or "处理失败，请稍后重试",
                    )
                )
            finally:
                if not state["saw_done"]:
                    fd = state["final_data"]
                    done_error = fd.get("error") if isinstance(fd, dict) else None
                    if isinstance(done_error, str) and done_error.strip():
                        await queue.put(
                            error_event(stage="chat", message=done_error)
                        )
                    elif (
                        not state["saw_error"]
                        and not state["assistant_content"].strip()
                        and not self._done_payload_has_content(fd)
                    ):
                        await queue.put(
                            error_event(
                                stage="chat",
                                message="模型未返回有效内容，请重试",
                            )
                        )
                    await queue.put(done_event(fd))

        producer_task = asyncio.create_task(_producer())
        try:
            while True:
                event = await queue.get()
                yield event
                if event.type is StreamEventType.DONE:
                    break
        finally:
            if not producer_task.done():
                producer_task.cancel()
                try:
                    await producer_task
                except (asyncio.CancelledError, Exception):
                    pass
