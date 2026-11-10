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
from app.services.agent_memory import (
    validate_memory, filter_history, is_management_request, is_observed_learning_statement,
)
from app.centers.exercise_center import ExerciseCenter
from app.centers.plan_center import PlanCenter
from app.centers.resource_center import ResourceCenter
from app.centers.chat_task_dispatcher import ChatTaskDispatcher
from app.centers.plan_builder import PlanBuilder
from app.centers.router_agent import RouterAgent
from app.centers.schemas import CenterTask, ExecutionPlan
from app.centers.visualization_center import VisualizationCenter
from app.events.types import (
    StreamEvent,
    StreamEventType,
    done_event,
    token_event,
    error_event,
    knowledge_candidates_event,
    recommendation_event,
)
from app.services.capability_gate import CapabilityGate, CapabilityKind
from app.services.capability_map import INTENT_CENTER_MAP, INTENT_DEPENDENCIES, KIND_TO_CENTER
from app.services.intent_extractor import IntentExtractor
from app.services.semantic_router import (
    SEMANTIC_TAKEOVER_CONFIDENCE,
    RouteState,
    classify,
    detect_compound_order,
    detect_referent,
    semantic_relabel,
)
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

# FINAL 实测：params 模型里 topic 的占位默认值；语义腿在无上文时（如"再来5道"）
# 会返回它，需要靠跨轮继承替换成真实主题。
_PLACEHOLDER_TOPIC = "AI基础"


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
        t4a_enabled: bool = False,
        semantic_extractor: Any | None = None,
        t4b_enabled: bool = False,
    ):
        self.router_agent = router_agent
        self.dispatcher = dispatcher
        self.capability_gate = capability_gate
        # P0-B：默认 dispatcher 路径要把旗标透传给 8 Agent + 5 Center。
        # 不透传时，BaseAgent 的默认 `use_mock_llm=False` 会**显式**阻断环境跟随，
        # 无 Key 环境在构造期抛 ValueError（见 tests/test_mock_llm_switch_contract.py）。
        self.use_mock_llm = use_mock_llm
        self._plan_builder = PlanBuilder()
        # T4-A：三态语义路由开关。默认关闭（旁路对照）；启用后 UNCERTAIN 态才会
        # 真正用语义重判接管路由。semantic_extractor 供测试注入（默认用 IntentExtractor，
        # 其 use_mock 跟随 INTENT_USE_LLM 环境变量，离线时走确定性关键词、不真调模型）。
        self.t4a_enabled = t4a_enabled
        self.semantic_extractor = semantic_extractor
        # T4-B：复合顺序重排开关。默认关闭（旁路只记录）；启用后按用户表达顺序重排多任务。
        self.t4b_enabled = t4b_enabled
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

    async def _semantic_audit_meta(
        self, message: str, gate_kind: str, gate_reason: str, gate_confidence: float
    ) -> tuple[dict, RouteState, tuple | None]:
        """T4-A 三态旁路判定：产出审计字段；返回三态与语义结果供启用接管复用。

        返回 (meta, state, semantic_result)：
        - meta：并入 intent_meta 的审计字段（不改执行）
        - state：三态（RouteState）
        - semantic_result：仅 UNCERTAIN 态为 (intents, is_clear, inquiry, latency, error)，
          其余态为 None。启用接管复用这份结果，**不重复调语义**（预算铁律：每请求 ≤1 次）。

        旁路约束：本方法**从不**影响 `route()` 返回的 ExecutionPlan 内容。
        """
        decision = classify(
            gate_kind=gate_kind,
            gate_reason=gate_reason,
            gate_confidence=gate_confidence,
            message=message,
        )
        meta: dict[str, Any] = {
            "semantic_state": decision.state.value,
        }
        semantic_result: tuple | None = None
        if decision.state is RouteState.UNCERTAIN:
            semantic_result = await semantic_relabel(
                message=message,
                intent_extractor=self.semantic_extractor,
            )
            intents, _confidences, is_clear, inquiry, latency, err, _params = semantic_result
            meta.update({
                "route_source": "semantic" if err is None else "fallback",
                "semantic_called": True,
                "semantic_latency_ms": latency,
                "semantic_error": err,
                "semantic_intents": intents,
                "semantic_is_clear": is_clear,
            })
        else:
            meta.update({
                "route_source": "rule",
                "semantic_called": False,
                "semantic_latency_ms": None,
                "semantic_error": None,
            })
        return meta, decision.state, semantic_result

    def _inherit_topic(self, context: dict | None, message: str) -> str:
        """从最近的上一轮 user 消息抽取主题，供跨轮指代（"再来5道"）继承。

        确定性、无 LLM：只取最近一条非当前的 user 消息，用关键词表/清洗抽 topic。
        抽不到则返回空串（调用方保持原样）。
        """
        msgs = list((context or {}).get("messages") or [])
        prev_user = ""
        for m in reversed(msgs):
            if m.get("role") == "user" and m.get("content") != message:
                prev_user = m.get("content", "")
                break
        if not prev_user:
            return ""
        try:
            from app.services.intent_extractor import _extract_topic

            topic = _extract_topic(prev_user)
        except Exception:
            return ""
        topic = (topic or "").strip()
        if not topic or topic == _PLACEHOLDER_TOPIC:
            return ""
        return topic

    def _takeover_plan(
        self,
        message: str,
        state: RouteState,
        semantic_result: tuple | None,
        student_profile: dict | None,
        context: dict | None,
        max_intents: int,
    ) -> ExecutionPlan | None:
        """启用接管的保守实现（仅 t4a_enabled=True 时由 route 调用）。

        只接管「不确定态 + 语义给出唯一、明确、非答疑的能力意图」这一种安全情形；
        其余一律返回 None（不接管，保持旧行为）。

        安全边界：
        - 只接受单一意图（len==1），排除多意图歧义
        - 排除 tutor_question / unknown（保持答疑兜底）
        - 意图必须映射到非 auto 的合法 center（auto 域不算"明确能力直通"）
        - 语义出错/不清不接管
        - 最高置信度 ≥ SEMANTIC_TAKEOVER_CONFIDENCE 才接管（挡未校准的伪置信误判）
        """
        if not self.t4a_enabled or state is not RouteState.UNCERTAIN:
            return None
        if semantic_result is None:
            return None
        intents, confidences, is_clear, _inquiry, _latency, err, sem_params = semantic_result
        if err is not None:
            return None
        if len(intents) != 1 or len(confidences) != 1:
            return None
        intent = intents[0]
        if intent in ("tutor_question", "unknown"):
            return None
        center = INTENT_CENTER_MAP.get(intent)
        if not center or center == "auto":
            return None
        # FINAL 实测修复：用语义腿给出的 params（含 count/difficulty/language），
        # 而非重建 —— 此前重建导致「生成一道题」的 count=1 丢失、落回默认 3。
        params = self._clean_params(dict(sem_params[0]) if sem_params else {})
        # FINAL 实测修复②：跨轮指代（"再来5道/再来几道"）语义腿看不到上文，topic 落成
        # 占位「AI基础」或 None，且 is_clear 恒为 False（模型因缺上文而"不确定"）。
        # 此时从上一条 user 消息继承主题；继承不到则按原规则拒绝（保持保守）。
        topic = str(params.get("topic") or "").strip()
        inherited_topic = ""
        if not topic or topic == _PLACEHOLDER_TOPIC:
            inherited_topic = self._inherit_topic(context, message)
            if inherited_topic:
                params["topic"] = inherited_topic
        # 明确指代 + 成功继承主题 → 放行（语义腿缺上文必然判 is_clear=False；
        # 意图本身可靠：量词"道/题"已足够定位为出题类）。
        referent_resolved = detect_referent(message) and bool(inherited_topic)
        if not referent_resolved:
            if not is_clear:
                return None
            if confidences[0] < SEMANTIC_TAKEOVER_CONFIDENCE:
                return None
        task = CenterTask(
            mode=center,
            intent=intent,
            input=message,
            params=params,
            context={**(context or {}), "student_profile": student_profile or {}},
            confidence=confidences[0],
        )
        return ExecutionPlan(
            tasks=[task],
            is_clear=True,
            intent_meta={"raw_message": message, "strategy": "t4a_takeover"},
            max_intents=max_intents,
        )

    @staticmethod
    def _clean_params(params: dict) -> dict:
        """清洗语义腿参数里的脏值。

        FINAL 实测：真模型偶发返回 count=None / count='more'（字符串）/ topic=None，
        这些脏值会直达下游 Center 并可能破坏参数校验，故在此归一。
        - count：只接受正整数，其余丢弃（下游回退默认值）
        - topic/difficulty/language：None 或空串丢弃
        """
        for key in ("topic", "difficulty", "language"):
            val = params.get(key)
            if val is None or (isinstance(val, str) and not val.strip()):
                params.pop(key, None)
        count = params.get("count")
        if isinstance(count, bool):
            params.pop("count", None)
        elif isinstance(count, int):
            if count <= 0:
                params.pop("count", None)
        elif isinstance(count, str):
            if count.strip().isdigit() and int(count) > 0:
                params["count"] = int(count)
            else:
                params.pop("count", None)
        elif count is not None:
            params.pop("count", None)
        return params

    def _reorder_by_compound(self, message: str, plan: ExecutionPlan) -> ExecutionPlan:
        """T4-B：按用户明确表达的顺序重排多任务（确定性、无 LLM）。

        仅当 `detect_compound_order` 识别出明确复合顺序、且任务数 ≥2、且各子句判出的
        意图与已识别任务意图**集合一致**时才重排。保守：只重排顺序，不增删任务、不引入
        子句新判出的意图（避免误加）。不满足条件则原样返回。
        """
        subclauses = detect_compound_order(message)
        if not subclauses or len(plan.tasks) < 2:
            return plan

        router = self._get_router()
        # 对每个子句粗判意图（仅取候选第一名），得到用户表达顺序的意图序列
        ordered_intents: list[str] = []
        for sub in subclauses:
            d = router.decide(sub)
            if d.candidates:
                ordered_intents.append(d.candidates[0].intent)

        if len(ordered_intents) < 2:
            return plan

        # 任务当前意图集合（保持多任务去重后的有序序列）
        task_intents = [t.intent for t in plan.tasks]
        # 仅当「子句判出的意图」与「任务意图」集合一致时才重排（否则保守不动）
        if set(ordered_intents) != set(task_intents):
            return plan

        # 按子句顺序映射到任务：对每个子句意图，取对应任务
        by_intent = {t.intent: t for t in plan.tasks}
        reordered = [by_intent[i] for i in ordered_intents if i in by_intent]
        if len(reordered) != len(plan.tasks):
            return plan
        for idx, t in enumerate(reordered):
            t.sequence = idx
        plan.tasks = reordered
        return plan

    def _compound_plan_from_semantic(
        self,
        message: str,
        semantic_result: tuple | None,
        student_profile: dict | None,
        context: dict | None,
        max_intents: int,
    ) -> ExecutionPlan | None:
        """T4-B：语义腿多意图 → 按返回顺序建多任务 plan（仅 t4b_enabled=True 时调用）。

        真模型语义腿对复合句已按表达顺序返回多意图（探针 5/5 对齐），故直接按语义返回顺序
        建任务。保守：仅接受 ≥2 个意图且每个意图映射到合法 center；否则返回 None 走原路径。
        """
        if not self.t4b_enabled or semantic_result is None:
            return None
        intents, confidences, is_clear, _inquiry, _latency, err, sem_params = semantic_result
        if err is not None or not is_clear:
            return None
        if len(intents) < 2:
            return None

        ctx = (context or {})
        tasks: list[Any] = []
        for idx, intent in enumerate(intents):
            center = INTENT_CENTER_MAP.get(intent)
            if not center:
                return None  # 含未知意图则整体放弃（保守）
            conf = confidences[idx] if idx < len(confidences) else 0.0
            # FINAL 实测修复：保留语义腿给出的 params（count/difficulty/language 等）
            p = dict(sem_params[idx]) if idx < len(sem_params) and sem_params[idx] else {}
            tasks.append(CenterTask(
                mode=center,
                intent=intent,
                input=message,
                params=p,
                context={**ctx, "student_profile": student_profile or {}},
                sequence=idx,
                confidence=conf,
            ))

        # T4-C：按意图级依赖表填 depends_on（真依赖，非顺序）。下游 intent 依赖的上游
        # intent 若在本计划内，则记其 sequence。
        for t in tasks:
            for upstream_intent in INTENT_DEPENDENCIES.get(t.intent, []):
                for up in tasks:
                    if up.intent == upstream_intent and up.sequence != t.sequence:
                        t.depends_on.append(up.sequence)

        return ExecutionPlan(
            tasks=tasks[:max_intents],
            is_clear=True,
            intent_meta={
                "raw_message": message,
                "strategy": "t4b_compound_semantic",
                "intents": [t.intent for t in tasks],
            },
            max_intents=max_intents,
        )

    def _referent_plan(
        self,
        message: str,
        context: dict | None,
        student_profile: dict | None,
        max_intents: int,
    ) -> ExecutionPlan | None:
        """T4-B：跨轮指代消解（仅 t4b_enabled=True 时调用）。

        当前消息是指代（"再来5道/画详细/改成两周"）且 history 上一轮有明确能力诉求时，
        复用上轮意图建单任务计划。找不到上轮明确意图则返回 None（走原 NORMAL_CHAT 兜底）。
        """
        if not self.t4b_enabled or not detect_referent(message):
            return None
        msgs = list((context or {}).get("messages") or [])
        # 从后往前找「上一轮 user 消息」：跳过末尾的当前消息
        prev_user = ""
        for m in reversed(msgs):
            if m.get("role") == "user" and m.get("content") != message:
                prev_user = m.get("content", "")
                break
        if not prev_user:
            return None
        rd = self._get_router().decide(prev_user)
        if not rd.candidates:
            return None
        intent = rd.candidates[0].intent
        if intent in ("tutor_question", "unknown"):
            return None
        center = INTENT_CENTER_MAP.get(intent)
        if not center:
            return None
        task = CenterTask(
            mode=center,
            intent=intent,
            input=message,
            params={},
            context={**(context or {}), "student_profile": student_profile or {}},
            confidence=rd.candidates[0].rule_score,
        )
        return ExecutionPlan(
            tasks=[task],
            is_clear=True,
            intent_meta={"raw_message": message, "strategy": "t4b_referent"},
            max_intents=max_intents,
        )

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
            plan = self._plan_builder.build(
                self._get_router().decide(message, mode),
                student_profile=student_profile,
                context=context,
                max_intents=max_intents,
            )
            # T4-A 旁路：空输入是确定行为（追问），记 semantic_state 但不调语义、
            # 不改执行，保证 140 条每条都有三态审计字段。
            plan.intent_meta.update({
                "semantic_state": "empty",
                "route_source": "rule",
                "semantic_called": False,
                "semantic_latency_ms": None,
                "semantic_error": None,
            })
            return plan

        # 一级判定：CapabilityGate。默认 NORMAL_CHAT 直达 TutorAgent，
        # 只有明确能力请求才进入 RouterAgent → ExecutionPlan → ChatTaskDispatcher。
        decision = self._get_gate().decide(
            message=message,
            mode=mode,
            student_profile=student_profile,
            context=context,
        )
        audit_meta = self._audit_context(message, context)
        # Real UI regression: "I finished indexes, next transactions" was already
        # persisted as progress, but an UNCERTAIN semantic guess created a plan.
        # Keep the gate's NORMAL_CHAT decision for a sourced statement alone.
        # Explicit modes/requests and unrelated inputs retain their old routing.
        if (decision.kind is CapabilityKind.NORMAL_CHAT
                and is_observed_learning_statement(message, (student_profile or {}).get("_agent_memory"))):
            return self._plan_builder.build_normal_chat(
                message, student_profile=student_profile, context=context,
                route="NORMAL_CHAT", reason="observed_learning_statement", confidence=1.0,
                audit_meta={**audit_meta, "semantic_state": "certain_normal", "route_source": "rule",
                            "semantic_called": False, "semantic_latency_ms": None, "semantic_error": None},
            )

        # T4-A 三态旁路：只记审计，不改返回的 plan（启用接管仅 t4a_enabled=True 时触发）
        semantic_meta, semantic_state, semantic_result = await self._semantic_audit_meta(
            message=message,
            gate_kind=decision.kind.value,
            gate_reason=decision.reason,
            gate_confidence=decision.confidence,
        )
        audit_meta = {**audit_meta, **semantic_meta}

        # T4-B 旁路：复合表达切分（只记审计，不改执行）。detect_compound_order 是确定性
        # 规则，切出的子句按用户表达顺序；仅写入 intent_meta 供对照表，不进脱敏审计白名单。
        compound_parts = detect_compound_order(message)
        if compound_parts:
            audit_meta = {
                **audit_meta,
                "compound_order": True,
                "compound_subclauses": compound_parts,
            }
        else:
            audit_meta = {**audit_meta, "compound_order": False}

        if decision.kind is CapabilityKind.NORMAL_CHAT:
            # T4-B：语义腿多意图 → 多任务 plan（救回复合句第二诉求）
            compound_plan = self._compound_plan_from_semantic(
                message=message,
                semantic_result=semantic_result,
                student_profile=student_profile,
                context=context,
                max_intents=max_intents,
            )
            if compound_plan is not None:
                return self._plan_builder.annotate_route(
                    compound_plan,
                    route=decision.kind.value,
                    reason=decision.reason,
                    audit_meta=audit_meta,
                )
            # T4-B：跨轮指代消解（"再来5道/画详细/改成两周"）复用上轮意图
            referent_plan = self._referent_plan(
                message=message,
                context=context,
                student_profile=student_profile,
                max_intents=max_intents,
            )
            if referent_plan is not None:
                return self._plan_builder.annotate_route(
                    referent_plan,
                    route=decision.kind.value,
                    reason=decision.reason,
                    audit_meta=audit_meta,
                )
            # 启用接管（保守）：不确定态且语义给出唯一明确能力 → 接管；
            # 否则回落原 NORMAL_CHAT。默认 t4a_enabled=False 时恒不接管。
            takeover = self._takeover_plan(
                message=message,
                state=semantic_state,
                semantic_result=semantic_result,
                student_profile=student_profile,
                context=context,
                max_intents=max_intents,
            )
            if takeover is not None:
                return self._plan_builder.annotate_route(
                    takeover,
                    route=decision.kind.value,
                    reason=decision.reason,
                    audit_meta=audit_meta,
                )
            return self._plan_builder.build_normal_chat(
                message,
                student_profile=student_profile,
                context=context,
                route=decision.kind.value,
                reason=decision.reason,
                confidence=decision.confidence,
                audit_meta=audit_meta,
            )

        router = self._get_router()

        # T4-B：语义腿多意图 → 多任务 plan（复合句 gate 命中能力也走这里救回第二诉求）
        compound_plan = self._compound_plan_from_semantic(
            message=message,
            semantic_result=semantic_result,
            student_profile=student_profile,
            context=context,
            max_intents=max_intents,
        )
        if compound_plan is not None:
            return self._plan_builder.annotate_route(
                compound_plan,
                route=decision.kind.value,
                reason=decision.reason,
                audit_meta=audit_meta,
            )

        plan = self._plan_builder.build(
            router.decide(message, mode),
            student_profile=student_profile,
            context=context,
            max_intents=max_intents,
        )
        # gate 判定了能力，二级路由必须进入对应中心，不得回落 tutor（Task 11 回归项）
        expected_center = KIND_TO_CENTER.get(decision.kind.value)
        if expected_center and not any(t.mode == expected_center for t in plan.tasks):
            # 二级关键词路由未命中 gate 判定的中心（回落 tutor）时，
            # 以显式 mode 直建对应中心的单任务计划，保证 gate 判定权威
            plan = self._plan_builder.build(
                router.decide(message, decision.kind.value.lower()),
                student_profile=student_profile,
                context=context,
                max_intents=max_intents,
            )
        # T4-B：启用时按用户表达顺序重排多任务（纯规则、超保守）
        if self.t4b_enabled:
            plan = self._reorder_by_compound(message, plan)

        # 能力路径同样带观测元数据，供 execute 边界产出审计日志
        return self._plan_builder.annotate_route(
            plan,
            route=decision.kind.value,
            reason=decision.reason,
            audit_meta=audit_meta,
        )

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
                    route_source=meta.get("route_source"),
                    semantic_state=meta.get("semantic_state"),
                    semantic_called=meta.get("semantic_called"),
                    semantic_latency_ms=meta.get("semantic_latency_ms"),
                    semantic_error=meta.get("semantic_error"),
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
        # Only the authenticated Java gateway constructs this data in production.
        # Envelope validation is defense in depth, not a substitute for service auth.
        raw_memory = (student_profile or {}).get("_agent_memory")
        memory = validate_memory(raw_memory, user_id=user_id, conversation_id=conversation_id)
        if raw_memory is not None:
            student_profile = {"_agent_memory": memory} if memory else {}
        if memory:
            history = filter_history(history, memory)
            reply = memory.get("command_reply")
            if reply and is_management_request(message):
                yield token_event(reply)
                yield done_event({"response": reply, "memory_command": True})
                return
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
