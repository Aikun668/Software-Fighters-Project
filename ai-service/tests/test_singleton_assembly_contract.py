"""单例装配区块契约（GUIDE P2 第 4 步 / Task 1）。

背景：48 个端点全部经由 18 个 `_get_xxx` 惰性单例工厂取依赖；`internal_api.py`
内 21 处 `Center/Agent/Workflow/Service` 构造 **全部落在工厂函数内部**，端点体内
0 处直连构造 —— 「唯一装配点」在六域收口时已达成。本轮只做收尾三件事：
统一锁语义、收拢声明、统一 docstring。**不改任何调用点，不改路由函数体。**

本文件分三部分：

- 第一部分 `ASM-C*`：**行为特征化**。重构前就应全绿，重构后仍须全绿，用来证明
  「没变坏」。其中 `ASM-C03` / `ASM-C04` 锁住 B 类注入点（直改模块级状态变量）
  的语义 —— 这是既有测试（`test_sse_contract.py`、`test_graph_endpoints_api_*.py`）
  赖以工作的前提，也是「工厂不能搬离 `internal_api` 模块」这一硬约束的来源。
- 第二部分 `ASM-S*`：**结构 RED**。`ASM-S01` / `ASM-S05` / `ASM-S06` 当前不满足
  （11 个工厂无锁、多数工厂无 docstring、声明散落 4 处），Task 2 / Task 3 后转绿。
  这是本步骤唯一「先红后绿」的证据。
- 第三部分 `ASM-E*`：同进程 ASGI 回归烟测（复用共享设施契约的 `SSE_CASES`）。

⚠️ 环境前提：`_get_mock_flag()` 硬编码 `False`，会让 13 个工厂因缺 API key 抛
`ValueError`。故本文件统一把 `_get_mock_flag` patch 成 `True`（与既有未跟踪脚本
`_accept_plan_endpoints.py:39` 同一手法）。**本轮不改 `_get_mock_flag` 本体** ——
它属 GUIDE 第 3 步「模型参数清洗」范畴，越界会让本轮验收边界模糊。
"""

import ast
import inspect
import threading
from pathlib import Path

import pytest

import internal_api
from tests.test_sse_shared_facilities_contract import SSE_CASE_NAMES, SSE_CASES, _make_app, _parse_events


AI_SERVICE_DIR = Path(internal_api.__file__).resolve().parent


# ═══════════════════════════════════════════════════════════════
# 装配清单（18 个惰性工厂 + 状态变量映射）
# ═══════════════════════════════════════════════════════════════

LAZY_FACTORIES = [
    "_get_chat_center",
    "_get_profile_agent",
    "_get_tutor_agent",
    "_get_tutor_center",
    "_get_content_agent",
    "_get_exercise_agent",
    "_get_exercise_center",
    "_get_path_agent",
    "_get_mindmap_agent",
    "_get_code_agent",
    "_get_profile_workflow",
    "_get_resource_center",
    "_get_path_workflow",
    "_get_inquiry_service",
    "_get_plan_center",
    "_get_graph_service",
    "_get_graph_center",
    "_get_intent_extractor",
]

# 工厂名 → 模块级状态变量名。`_get_intent_extractor` 是例外：无 `_singleton` 后缀。
SINGLETON_OF = {
    "_get_chat_center": "_chat_center_singleton",
    "_get_profile_agent": "_profile_agent_singleton",
    "_get_tutor_agent": "_tutor_agent_singleton",
    "_get_tutor_center": "_tutor_center_singleton",
    "_get_content_agent": "_content_agent_singleton",
    "_get_exercise_agent": "_exercise_agent_singleton",
    "_get_exercise_center": "_exercise_center_singleton",
    "_get_path_agent": "_path_agent_singleton",
    "_get_mindmap_agent": "_mindmap_agent_singleton",
    "_get_code_agent": "_code_agent_singleton",
    "_get_profile_workflow": "_profile_workflow_singleton",
    "_get_resource_center": "_resource_center_singleton",
    "_get_path_workflow": "_path_workflow_singleton",
    "_get_inquiry_service": "_inquiry_service_singleton",
    "_get_plan_center": "_plan_center_singleton",
    "_get_graph_service": "_graph_service_singleton",
    "_get_graph_center": "_graph_center_singleton",
    "_get_intent_extractor": "_intent_extractor",
}

# 收口前已带双检锁的 7 个（ASM-S02 要求不回退）；其余 11 个由 Task 2 补齐。
ALREADY_LOCKED = [
    "_get_chat_center",
    "_get_tutor_center",
    "_get_exercise_center",
    "_get_resource_center",
    "_get_plan_center",
    "_get_graph_center",
    "_get_intent_extractor",
]
UNLOCKED_FACTORIES = [name for name in LAZY_FACTORIES if name not in ALREADY_LOCKED]

# `_get_graph_service()` 转调 `app.services.graph_service.get_graph_service()`，
# 后者自身是模块级单例 —— 状态下零后重建会拿回**同一个**实例，故不适用「重建出新对象」。
REBUILD_EXCLUDED = {"_get_graph_service"}

LOCK_OF = {name: f"_{name[len('_get_'):]}_lock" for name in LAZY_FACTORIES}


def _dump_source() -> str:
    return Path(internal_api.__file__).read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
# Fixture —— patch mock_flag + 复位全部单例状态
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def wired(monkeypatch):
    """强制 mock LLM 可用，并保证用例结束后 18 个状态变量与 GraphService 外部单例复原。

    `app.services.graph_service._graph_service` 一并复位，避免内存态跨用例泄漏
    （与 `test_graph_endpoints_api_delegation._fresh_state()` 同一顾虑）。
    """
    from app.services import graph_service as graph_service_module

    monkeypatch.setattr(internal_api, "_get_mock_flag", lambda: True)

    saved = {name: getattr(internal_api, name) for name in SINGLETON_OF.values()}
    saved_graph = graph_service_module._graph_service

    for name in SINGLETON_OF.values():
        setattr(internal_api, name, None)

    try:
        yield
    finally:
        for name, value in saved.items():
            setattr(internal_api, name, value)
        graph_service_module._graph_service = saved_graph


# ═══════════════════════════════════════════════════════════════
# 第一部分 ASM-C* —— 行为特征化（重构前后都必须绿）
# ═══════════════════════════════════════════════════════════════


class TestAssemblyBehaviour:

    def test_asm_c01_all_lazy_factory_names_exist_and_are_callable(self):
        for name in LAZY_FACTORIES:
            assert hasattr(internal_api, name), f"{name} 缺失"
            assert callable(getattr(internal_api, name)), f"{name} 不可调用"

    def test_asm_c02_each_factory_returns_the_same_instance(self, wired):
        for name in LAZY_FACTORIES:
            factory = getattr(internal_api, name)
            first, second = factory(), factory()
            assert first is second, f"{name} 不是单例"

    def test_asm_c03_direct_state_write_is_honoured(self, wired):
        """B 类注入点：`internal_api._x_singleton = stub` 必须被工厂读到。

        既有测试 `test_sse_contract.py:110` 与 `test_graph_endpoints_api_*.py`
        直接改写这些模块级变量，本断言即该用法的契约化。
        """
        sentinel = object()
        for factory_name, state_name in SINGLETON_OF.items():
            setattr(internal_api, state_name, sentinel)
            got = getattr(internal_api, factory_name)()
            assert got is sentinel, f"{factory_name} 未读取 {state_name}"

    def test_asm_c04_none_state_triggers_rebuild(self, wired):
        """复位语义：状态置 None 后工厂重新构造（`_fresh_state()` 依赖此行为）。"""
        for name in LAZY_FACTORIES:
            if name in REBUILD_EXCLUDED:
                continue
            factory = getattr(internal_api, name)
            first = factory()
            setattr(internal_api, SINGLETON_OF[name], None)
            second = factory()
            assert second is not first, f"{name} 在状态复位后未重建"

    def test_asm_c05_tutor_center_injects_agent_singletons(self, wired):
        center = internal_api._get_tutor_center()
        assert center.tutor_agent is internal_api._get_tutor_agent()
        assert center.profile_agent is internal_api._get_profile_agent()

    def test_asm_c06_exercise_center_injects_exercise_agent_singleton(self, wired):
        center = internal_api._get_exercise_center()
        assert center.exercise_agent is internal_api._get_exercise_agent()

    def test_asm_c07_plan_center_injects_exercise_center_singleton(self, wired):
        center = internal_api._get_plan_center()
        assert center.exercise_center is internal_api._get_exercise_center()

    def test_asm_c08_graph_center_injects_graph_service_singleton(self, wired):
        center = internal_api._get_graph_center()
        assert center._graph_service is internal_api._get_graph_service()

    def test_asm_c09_graph_service_delegates_to_service_module(self, wired):
        from app.services import graph_service as graph_service_module

        assert internal_api._get_graph_service() is graph_service_module.get_graph_service()

    def test_asm_c10_mock_flag_is_still_false(self):
        """本轮明确不动 `_get_mock_flag`（属 GUIDE 第 3 步，越界）。"""
        assert internal_api._get_mock_flag() is False

    def test_asm_c11_endpoints_have_no_direct_construction(self):
        """唯一装配点不回退：端点体内不得直接构造 Center/Agent/Workflow/Service。"""
        tree = ast.parse(_dump_source())
        suffixes = ("Center", "Agent", "Workflow", "Service")
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorators = [ast.unparse(d) for d in node.decorator_list]
            if not any("router." in d for d in decorators):
                continue
            for call in ast.walk(node):
                if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)):
                    continue
                name = call.func.id
                if name.endswith(suffixes) and not name.startswith("_get_"):
                    offenders.append(f"{node.name}:{call.lineno} {name}")
        assert offenders == [], f"端点内直连构造：{offenders}"

    def test_asm_c12_removed_factories_stay_removed(self):
        for name in ("_get_solve_agent", "_get_plan_status_core", "_get_resource_workflow"):
            assert not hasattr(internal_api, name), f"{name} 复活了"

    def test_asm_c13_graph_factories_stay_present(self):
        for name in ("_get_graph_center", "_get_graph_service"):
            assert hasattr(internal_api, name), f"{name} 消失"


# ═══════════════════════════════════════════════════════════════
# 第二部分 ASM-S* —— 结构 RED（Task 2 / Task 3 转绿）
# ═══════════════════════════════════════════════════════════════


class TestAssemblyStructure:

    @pytest.mark.parametrize("factory_name", UNLOCKED_FACTORIES)
    def test_asm_s01_unlocked_factories_gain_double_checked_lock(self, factory_name):
        """11 个裸 `if None` 工厂必须补齐与另 7 个一致的双检锁。"""
        source = inspect.getsource(getattr(internal_api, factory_name))
        lock_name = LOCK_OF[factory_name]
        assert f"with {lock_name}" in source, f"{factory_name} 仍无锁"

    @pytest.mark.parametrize("factory_name", ALREADY_LOCKED)
    def test_asm_s02_locked_factories_keep_their_lock(self, factory_name):
        source = inspect.getsource(getattr(internal_api, factory_name))
        assert f"with {LOCK_OF[factory_name]}" in source, f"{factory_name} 锁被移除"

    def test_asm_s03_every_factory_has_a_lock_object(self, wired):
        for name in LAZY_FACTORIES:
            lock = getattr(internal_api, LOCK_OF[name], None)
            assert lock is not None, f"{LOCK_OF[name]} 缺失"
            assert isinstance(lock, type(threading.Lock())), f"{LOCK_OF[name]} 不是 Lock"

    def test_asm_s04_factory_bodies_stay_synchronous(self):
        """工厂体内不得出现 `await`。

        这是「无锁工厂在 asyncio 单线程下不会真的重复构造」这一前提的固化；
        一旦将来引入异步初始化，本断言会先红，提示补真正的并发测试。
        """
        for name in LAZY_FACTORIES:
            tree = ast.parse(inspect.getsource(getattr(internal_api, name)))
            assert not any(isinstance(n, ast.Await) for n in ast.walk(tree)), f"{name} 含 await"

    def test_asm_s05_every_factory_documents_its_patch_target(self):
        for name in LAZY_FACTORIES:
            doc = inspect.getdoc(getattr(internal_api, name)) or ""
            assert doc, f"{name} 无 docstring"
            assert "测试 patch 目标" in doc, f"{name} docstring 未写明测试 patch 目标"

    def test_asm_s06_declarations_form_one_block_ahead_of_routes(self):
        """装配声明必须集中成一个区块，且整体位于路由区之前。"""
        tree = ast.parse(_dump_source())

        declarations = []
        first_route = None
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                decorators = [ast.unparse(d) for d in node.decorator_list]
                if first_route is None and any("router." in d for d in decorators):
                    first_route = node.lineno
                continue
            targets = []
            if isinstance(node, ast.Assign):
                targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                targets = [node.target.id]
            for name in targets:
                if name.endswith("_singleton") or name.endswith("_lock") or name == "_intent_extractor":
                    declarations.append((name, node.lineno))

        assert declarations, "未找到任何装配声明"
        assert first_route is not None, "未找到路由函数"

        late = [(n, ln) for n, ln in declarations if ln > first_route]
        assert late == [], f"装配声明散落在路由区之后：{late}"

        lines = sorted(ln for _, ln in declarations)
        gap = max(b - a for a, b in zip(lines, lines[1:]))
        assert gap <= 40, f"装配声明跨度 {gap} 行，未收拢成单一区块：{declarations}"


# ═══════════════════════════════════════════════════════════════
# 第三部分 ASM-E* —— 同进程 ASGI 回归烟测
# ═══════════════════════════════════════════════════════════════


class TestAssemblyEndToEnd:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("case_name", SSE_CASE_NAMES)
    async def test_asm_e01_sse_endpoints_still_emit_exactly_one_done(self, monkeypatch, case_name):
        """8 个 SSE 端点经装配区块取依赖后，仍恰好产出 1 个 done 且位于末位。"""
        from httpx import ASGITransport, AsyncClient

        path, payload, install = SSE_CASES[case_name]
        install(monkeypatch)

        async with AsyncClient(
            transport=ASGITransport(app=_make_app()), base_url="http://test",
        ) as client:
            async with client.stream("POST", path, json=payload) as resp:
                body = "".join([chunk async for chunk in resp.aiter_text()])
                assert resp.status_code == 200, case_name

        events = _parse_events(body)
        assert events, f"{case_name} 未产生事件"
        types = [e.get("type") for e in events]
        assert types.count("done") == 1, (case_name, types)
        assert types[-1] == "done", (case_name, types)
