import logging
import time

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
from app.centers.result_agent import ResultAgent
from app.centers.router_agent import RouterAgent
from app.centers.schemas import CenterTask, ExecutionPlan
from app.centers.visualization_center import VisualizationCenter
from app.events.types import StreamEventType
from app.services.capability_gate import CapabilityGate, CapabilityKind
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

# CapabilityKind → ResultAgent 编排中心（Task 11 评审回归项：
# gate 判定了能力，二级路由就必须进入对应中心，不得回落 tutor）
_KIND_TO_CENTER = {
    "PLAN": "plan",
    "RESOURCE": "resource",
    "EXERCISE": "exercise",
    "VISUALIZATION": "visualization",
}


class ChatCenter:
    def __init__(
        self,
        router_agent: RouterAgent | None = None,
        result_agent: ResultAgent | None = None,
        capability_gate: CapabilityGate | None = None,
    ):
        self.router_agent = router_agent
        self.result_agent = result_agent
        self.capability_gate = capability_gate

    def _get_router(self) -> RouterAgent:
        if self.router_agent is None:
            self.router_agent = RouterAgent(intent_extractor=IntentExtractor())
        return self.router_agent

    def _get_gate(self) -> CapabilityGate:
        if self.capability_gate is None:
            self.capability_gate = CapabilityGate()
        return self.capability_gate

    def _get_result(self) -> ResultAgent:
        if self.result_agent is None:
            decompose = DecomposeAgent()
            goal = GoalAgent()
            schedule = ScheduleAgent()
            adjustment = AdjustmentAgent()
            diagnose = DiagnoseAgent()
            profile = ProfileAgent()
            exercise = ExerciseAgent(model_profile=PROFILE_EXERCISE)
            content = ContentAgent()

            self.result_agent = ResultAgent(
                auto_center=AutoCenter(
                    diagnose_agent=diagnose,
                    profile_agent=profile,
                ),
                plan_center=PlanCenter(
                    goal_agent=goal,
                    decompose_agent=decompose,
                    schedule_agent=schedule,
                    adjustment_agent=adjustment,
                ),
                resource_center=ResourceCenter(
                    content_agent=content,
                ),
                exercise_center=ExerciseCenter(
                    exercise_agent=exercise,
                ),
                visualization_center=VisualizationCenter(),
            )
        return self.result_agent

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
        # 只有明确能力请求才进入 RouterAgent → ExecutionPlan → ResultAgent。
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
        expected_center = _KIND_TO_CENTER.get(decision.kind.value)
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
        result = self._get_result()

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
