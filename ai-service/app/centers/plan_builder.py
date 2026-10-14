"""计划构建：把意图决策（`RouteDecision`）翻译为可执行的 `ExecutionPlan`。

【决策所有权】执行计划的唯一构造者 —— 选 Center（读 `capability_map`）、排顺序、
  置确认标记。输入只读 `RouteDecision`，不重新判断用户意图。
  - 唯一调用点：`ChatCenter.route`（`RouterAgent.route` 仅作旧测试兼容的组合入口）
  - 禁止：识别意图、调用 LLM、派发执行
"""

from app.centers.route_decision import RouteDecision
from app.centers.schemas import CenterTask, ExecutionPlan
from app.services.capability_map import CENTER_EXECUTION_ORDER, INTENT_CENTER_MAP

# 超过此数量触发确认卡
_CONFIRM_THRESHOLD = 3


class PlanBuilder:
    def build(
        self,
        decision: RouteDecision,
        *,
        student_profile: dict | None = None,
        context: dict | None = None,
        max_intents: int = 3,
    ) -> ExecutionPlan:
        student_profile = student_profile or {}
        context = context or {}
        if decision.source == "empty":
            return self._inquiry_plan(decision, student_profile, context)
        if decision.source == "manual":
            return self._manual_plan(decision, student_profile, context)
        if decision.source == "keyword":
            return self._keyword_plan(decision, student_profile, context, max_intents)
        return self._fallback_plan(decision, student_profile, context)

    def build_normal_chat(
        self,
        message: str,
        *,
        student_profile: dict | None,
        context: dict | None,
        route: str,
        reason: str,
        confidence: float,
        audit_meta: dict,
    ) -> ExecutionPlan:
        context = context or {}
        task = CenterTask(
            mode="auto",
            intent="tutor_question",
            input=message,
            params={"question": message.strip()},
            context={
                **context,
                "student_profile": student_profile or {},
                "capability_route": route,
                "capability_reason": reason,
            },
            confidence=confidence,
        )
        return ExecutionPlan(
            tasks=[task],
            is_clear=True,
            intent_meta={
                "raw_message": message,
                "strategy": "capability_gate",
                "route": route,
                "route_reason": reason,
                **audit_meta,
            },
        )

    @staticmethod
    def annotate_route(
        plan: ExecutionPlan, *, route: str, reason: str, audit_meta: dict
    ) -> ExecutionPlan:
        plan.intent_meta.update({
            "route": route,
            "route_reason": reason,
            **audit_meta,
        })
        return plan

    @staticmethod
    def _task_context(context: dict, student_profile: dict) -> dict:
        return {**context, "student_profile": student_profile}

    def _inquiry_plan(
        self, decision: RouteDecision, student_profile: dict, context: dict
    ) -> ExecutionPlan:
        task = CenterTask(
            mode="inquiry",
            intent="inquiry",
            input=decision.message,
            params={"question": decision.inquiry},
            context=self._task_context(context, student_profile),
            confidence=0.0,
        )
        return ExecutionPlan(
            tasks=[task],
            is_clear=False,
            intent_meta={"raw_message": decision.message, "strategy": "empty_inquiry"},
        )

    def _manual_plan(
        self, decision: RouteDecision, student_profile: dict, context: dict
    ) -> ExecutionPlan:
        candidate = decision.candidates[0]
        task = CenterTask(
            mode=INTENT_CENTER_MAP.get(candidate.intent, "auto"),
            intent=candidate.intent,
            input=decision.message,
            params=candidate.params,
            context={
                **self._task_context(context, student_profile),
                "manual_mode": decision.manual_mode,
            },
            confidence=candidate.rule_score,
        )
        return ExecutionPlan(
            tasks=[task],
            is_clear=True,
            intent_meta={
                "manual_mode": decision.manual_mode,
                "raw_message": decision.message,
            },
        )

    def _keyword_plan(
        self,
        decision: RouteDecision,
        student_profile: dict,
        context: dict,
        max_intents: int,
    ) -> ExecutionPlan:
        tasks = [
            CenterTask(
                mode=INTENT_CENTER_MAP.get(c.intent, "auto"),
                intent=c.intent,
                input=decision.message,
                params=c.params,
                context=self._task_context(context, student_profile),
                sequence=idx,
                confidence=c.rule_score,
            )
            for idx, c in enumerate(decision.candidates)
        ]
        tasks = self._sort_by_confidence(tasks)
        needs_confirm = len(tasks) >= _CONFIRM_THRESHOLD
        return ExecutionPlan(
            tasks=tasks,
            is_clear=True,
            needs_confirmation=needs_confirm,
            intent_meta={
                "raw_message": decision.message,
                "intents": [t.intent for t in tasks],
                "confidence": [t.confidence for t in tasks],
                "strategy": "keyword",
                "needs_confirmation": needs_confirm,
            },
            max_intents=max_intents,
        )

    def _fallback_plan(
        self, decision: RouteDecision, student_profile: dict, context: dict
    ) -> ExecutionPlan:
        candidate = decision.candidates[0]
        task = CenterTask(
            mode=INTENT_CENTER_MAP.get(candidate.intent, "auto"),
            intent=candidate.intent,
            input=decision.message,
            params=candidate.params,
            context=self._task_context(context, student_profile),
            confidence=candidate.rule_score,
        )
        return ExecutionPlan(
            tasks=[task],
            is_clear=True,
            intent_meta={"raw_message": decision.message, "strategy": "fallback_tutor"},
        )

    @staticmethod
    def _sort_by_confidence(tasks: list[CenterTask]) -> list[CenterTask]:
        tasks.sort(
            key=lambda t: (-t.confidence, CENTER_EXECUTION_ORDER.get(t.mode, 99))
        )
        for idx, task in enumerate(tasks):
            task.sequence = idx
        return tasks
