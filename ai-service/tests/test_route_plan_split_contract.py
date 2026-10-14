"""T2/T3 契约：意图决策 ≠ 计划构建；执行前裁决唯一；执行层不重判全局意图。"""

import ast
from pathlib import Path

import pytest

from app.centers.chat_task_dispatcher import ChatTaskDispatcher
from app.centers.execution_gate import ExecutionVerdict, blocks_execution, judge
from app.centers.plan_builder import PlanBuilder
from app.centers.route_decision import RouteDecision
from app.centers.router_agent import RouterAgent
from app.centers.schemas import CenterResult, CenterTask, ExecutionPlan
from app.events.types import StreamEventType
from app.services.capability_map import CENTER_EXECUTION_ORDER, INTENT_CENTER_MAP

APP_DIR = Path(__file__).resolve().parent.parent / "app"
CENTERS_DIR = APP_DIR / "centers"

# 执行层：只执行已确定的任务，不得依赖任何意图判定 / 计划构建模块
EXECUTION_LAYER_FILES = [
    "chat_task_dispatcher.py",
    "auto_center.py",
    "plan_center.py",
    "resource_center.py",
    "exercise_center.py",
    "visualization_center.py",
]
INTENT_SIDE_MODULES = (
    "app.centers.route_decision",
    "app.centers.plan_builder",
    "app.centers.router_agent",
    "app.services.intent_extractor",
    "app.services.capability_gate",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            mods.add(node.module)
        elif isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
    return mods


def _names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


# ── T2：意图决策只产 RouteDecision ───────────────────────────────


class TestIntentDecisionOnly:
    def test_decide_empty_message_is_inquiry(self):
        d = RouterAgent().decide("   ")
        assert d.source == "empty"
        assert d.is_clear is False
        assert d.inquiry == "你想了解什么？"
        assert d.candidates == ()

    def test_decide_manual_mode_uses_mode_table(self):
        d = RouterAgent().decide("讲一下二叉树", mode="exercise")
        assert d.source == "manual"
        assert d.manual_mode == "exercise"
        assert [c.intent for c in d.candidates] == ["exercise_gen"]
        assert d.candidates[0].rule_score == 1.0

    def test_decide_keyword_multi_candidates(self):
        d = RouterAgent().decide("帮我规划学习路线，并推荐一些资料")
        assert d.source == "keyword"
        assert {c.intent for c in d.candidates} >= {"learning_path", "resource_gen"}

    def test_decide_fallback_is_tutor_with_zero_score(self):
        d = RouterAgent().decide("嗯")
        assert d.source == "fallback"
        assert [c.intent for c in d.candidates] == ["tutor_question"]
        assert d.candidates[0].rule_score == 0.0

    def test_router_agent_does_not_construct_tasks_or_plans(self):
        path = CENTERS_DIR / "router_agent.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert "CenterTask" not in _names(path)
        calls = [
            n.func.id
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        ]
        assert "ExecutionPlan" not in calls

    def test_decision_does_not_pick_center_or_order(self):
        fields = set(RouteDecision.__dataclass_fields__)
        assert not ({"center", "mode_center", "execution_order", "sequence"} & fields)


# ── T2：计划构建不重新猜意图 ─────────────────────────────────────


class TestPlanBuilderOnly:
    def test_plan_builder_has_no_intent_side_imports(self):
        mods = _imports(CENTERS_DIR / "plan_builder.py")
        banned = {
            "app.centers.router_agent",
            "app.services.intent_extractor",
            "app.services.capability_gate",
        }
        assert not (mods & banned)

    def test_single_task_plan(self):
        d = RouterAgent().decide("给我出 5 道二叉树练习题")
        plan = PlanBuilder().build(d)
        assert [(t.mode, t.intent, t.sequence) for t in plan.tasks] == [
            ("exercise", "exercise_gen", 0)
        ]
        assert plan.intent_meta["strategy"] == "keyword"

    def test_multi_task_plan_follows_confidence_then_center_order(self):
        d = RouterAgent().decide("帮我规划学习路线，并推荐一些资料")
        plan = PlanBuilder().build(d)
        assert [(t.mode, t.intent, t.sequence) for t in plan.tasks] == [
            ("plan", "learning_path", 0),
            ("resource", "resource_gen", 1),
        ]

    def test_centers_come_from_the_single_source(self):
        d = RouterAgent().decide("画一张 TCP 三次握手流程图")
        plan = PlanBuilder().build(d)
        for t in plan.tasks:
            assert t.mode == INTENT_CENTER_MAP[t.intent]

    def test_empty_decision_builds_inquiry_plan(self):
        plan = PlanBuilder().build(RouterAgent().decide(""))
        assert plan.is_clear is False
        assert plan.tasks[0].mode == "inquiry"
        assert plan.tasks[0].params == {"question": "你想了解什么？"}
        assert plan.intent_meta["strategy"] == "empty_inquiry"

    def test_manual_plan_meta(self):
        plan = PlanBuilder().build(RouterAgent().decide("x", mode="plan"))
        assert plan.intent_meta == {"manual_mode": "plan", "raw_message": "x"}
        assert plan.tasks[0].context["manual_mode"] == "plan"

    def test_three_intents_set_needs_confirmation(self):
        plan = PlanBuilder().build(
            RouterAgent().decide("规划学习路径，出几道练习题，再画流程图并生成讲义")
        )
        assert plan.needs_confirmation == (len(plan.tasks) >= 3)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "message,mode",
        [
            ("什么是进程和线程的区别", "auto"),
            ("给我出 5 道二叉树练习题", "auto"),
            ("帮我规划学习路线，并推荐一些资料", "auto"),
            ("画一张 TCP 三次握手流程图", "auto"),
            ("生成反向传播技术文档", "auto"),
            ("随便聊聊", "plan"),
            ("", "auto"),
            ("嗯", "auto"),
        ],
    )
    async def test_router_route_shim_equals_decide_plus_build(self, message, mode):
        router = RouterAgent()
        via_shim = await router.route(message, mode=mode, max_intents=3)
        via_split = PlanBuilder().build(router.decide(message, mode), max_intents=3)
        assert via_shim == via_split


# ── T2：执行前裁决唯一 ───────────────────────────────────────────


class _StubCenter:
    def __init__(self):
        self.calls = 0

    async def execute(self, task, on_token=None):
        self.calls += 1
        return CenterResult(
            mode=task.mode,
            intent=task.intent,
            payload={"response": "ok"},
            agent="stub",
            sequence=task.sequence,
        )


async def _drain(dispatcher, plan):
    return [e async for e in dispatcher.execute(plan)]


class TestExecutionGate:
    def test_judge_pass_inquiry_confirm(self):
        task = CenterTask(mode="auto", intent="tutor_question", input="x")
        assert judge(ExecutionPlan(tasks=[task])) is ExecutionVerdict.PASS
        inquiry = CenterTask(mode="inquiry", intent="inquiry", input="")
        assert judge(ExecutionPlan(tasks=[inquiry], is_clear=False)) is ExecutionVerdict.INQUIRY
        assert (
            judge(ExecutionPlan(tasks=[task], needs_confirmation=True))
            is ExecutionVerdict.CONFIRM
        )

    def test_only_inquiry_blocks_execution(self):
        assert blocks_execution(ExecutionVerdict.INQUIRY)
        assert not blocks_execution(ExecutionVerdict.CONFIRM)
        assert not blocks_execution(ExecutionVerdict.PASS)

    @pytest.mark.asyncio
    async def test_dispatcher_emits_inquiry_and_skips_centers(self):
        dispatcher = ChatTaskDispatcher(use_mock_llm=True)
        stub = _StubCenter()
        dispatcher.auto_center = stub
        plan = PlanBuilder().build(RouterAgent().decide(""))
        events = await _drain(dispatcher, plan)
        types = [e.type for e in events]
        assert types == [StreamEventType.INQUIRY, StreamEventType.DONE]
        assert stub.calls == 0

    @pytest.mark.asyncio
    async def test_confirm_verdict_still_executes_as_before(self):
        dispatcher = ChatTaskDispatcher(use_mock_llm=True)
        stub = _StubCenter()
        dispatcher.auto_center = stub
        task = CenterTask(mode="auto", intent="tutor_question", input="x")
        plan = ExecutionPlan(tasks=[task], needs_confirmation=True)
        events = await _drain(dispatcher, plan)
        assert stub.calls == 1
        assert events[-1].type is StreamEventType.DONE


# ── T3：执行层边界 ───────────────────────────────────────────────


class TestExecutionLayerBoundary:
    @pytest.mark.parametrize("filename", EXECUTION_LAYER_FILES)
    def test_execution_layer_does_not_import_intent_side(self, filename):
        mods = _imports(CENTERS_DIR / filename)
        offenders = {
            m for m in mods for t in INTENT_SIDE_MODULES if m == t or m.startswith(t + ".")
        }
        assert offenders == set(), f"{filename} 依赖意图判定侧：{offenders}"

    def test_dispatcher_centers_match_execution_order_table(self):
        dispatcher = ChatTaskDispatcher(use_mock_llm=True)
        resolvable = {m for m in CENTER_EXECUTION_ORDER if dispatcher._center_for(m)}
        assert resolvable == set(CENTER_EXECUTION_ORDER)

    def test_every_mapped_center_is_resolvable_by_dispatcher(self):
        dispatcher = ChatTaskDispatcher(use_mock_llm=True)
        for intent, center in INTENT_CENTER_MAP.items():
            assert dispatcher._center_for(center) is not None, (intent, center)

    def test_unknown_mode_is_not_resolvable(self):
        assert ChatTaskDispatcher(use_mock_llm=True)._center_for("__nope__") is None
