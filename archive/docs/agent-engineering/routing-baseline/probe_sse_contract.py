"""T0.4 · 冻结重构前 ChatCenter.stream_chat 的 SSE 事件契约（只读）。

[只读] 用 **测试替身** 隔离 LLM 与 DB，驱动**真实入口** `ChatCenter.stream_chat()`：

- LLM 隔离：`ChatCenter(use_mock_llm=True)` —— 透传到 8 Agent + 5 Center，
  全程 mock 流，无网络调用；无需 API Key。
- DB/推荐隔离：实例级 stub `center._extract_knowledge_nodes` 返回空分组，
  既不触发 LLM 抽取，也不产生 recommendation / knowledge_candidates 事件。
- 不写库、不改生产代码、不改路由映射。

覆盖 5 条链路：普通答疑 / 生成练习 / 学习资源 / 学习规划 / 可视化。

另加 4 条**终态合同**用例（异常/提前终止），用可编程 dispatcher 替身驱动
`ChatCenter.stream_chat`：缺 done 补发 / 多 done 收敛 / 管线异常转 error / 追问不误判。

记录内容（逐事件）：
- 事件类型 + stage + **载荷字段结构**（键名/嵌套形状，不含随机正文）
- 连续 TOKEN 折叠为一组（count + 总字符数）
- 终止规则：末帧是否 done、done 是否唯一、是否出现 error
- 每条链路跑两次，逐字段比对 → 确定性

非确定正文一律归一（token 只记字符数、shape 只记类型结构）；无法离线验证的
项显式标 UNVERIFIED，**不伪造**。真实 LLM 才能触发的分支（如真实超时文案、
检索命中差异）不在本探针覆盖范围 → UNVERIFIED（见 T0-handoff.md）。

运行（Windows/中文控制台）：
    cd ai-service
    PYTHONUTF8=1 python ../docs/agent-engineering/routing-baseline/probe_sse_contract.py
"""
import asyncio
import io
import json
import os
import sys
from typing import Any, AsyncIterator

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
AI_SERVICE = os.path.abspath(os.path.join(HERE, "..", "..", "..", "ai-service"))
sys.path.insert(0, AI_SERVICE)

from app.centers.chat_center import ChatCenter  # noqa: E402
from app.centers.schemas import CenterTask, ExecutionPlan  # noqa: E402
from app.events.types import (  # noqa: E402
    StreamEvent,
    StreamEventType,
    done_event,
    inquiry_event,
    token_event,
)

OUT = os.path.join(HERE, "sse_contract.json")

# 5 条评测链路：mode 固定（确定性），message 触发对应能力。
CHAINS: list[dict] = [
    {"chain": "普通答疑", "mode": "auto", "message": "什么是进程和线程的区别"},
    {"chain": "生成练习", "mode": "auto", "message": "给我出 5 道二叉树练习题"},
    {"chain": "学习资源", "mode": "auto", "message": "生成反向传播技术文档"},
    {"chain": "学习规划", "mode": "auto", "message": "帮我规划学习路线，并推荐一些资料"},
    {"chain": "可视化", "mode": "auto", "message": "画一张 TCP 三次握手流程图"},
]


async def _stub_extract(*args: Any, **kwargs: Any) -> dict:
    """推荐抽取替身：空分组 → 不产生推荐事件，不触碰 LLM。"""
    return {"primary": [], "related": [], "broad": [], "all": []}


def _shape(value: Any) -> Any:
    """结构指纹：只保留类型/键名，丢弃随机正文与长度。"""
    if isinstance(value, dict):
        return {k: _shape(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return ["[list]", _shape(value[0])] if value else ["[list]"]
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "num"
    if isinstance(value, str):
        return "str"
    if value is None:
        return "null"
    return type(value).__name__


def _payload(ev: StreamEvent) -> dict:
    """把 `to_sse()` 的 SSE 字符串还原为顶层 payload 字典。"""
    raw = ev.to_sse()
    body = raw[len("data: "):].rstrip("\n") if raw.startswith("data: ") else raw
    return json.loads(body)


def _token_chars(payload: dict) -> int:
    # token 事件在 to_sse() 里把 data 平铺到顶层，正文位于顶层 content 键。
    content = payload.get("content", "")
    return len(content) if isinstance(content, str) else 0


def _describe(ev: StreamEvent) -> dict:
    payload = _payload(ev)
    return {
        "type": ev.type.name,
        "stage": payload.get("stage", ""),
        "keys": sorted(payload.keys()),
        "shape": _shape({k: v for k, v in payload.items() if k not in ("stage", "message")}),
    }


def _compress(events: list[StreamEvent]) -> list[dict]:
    """连续 TOKEN 折叠；其余逐帧记录类型/stage/键/结构。"""
    out: list[dict] = []
    for ev in events:
        if ev.type.name == "TOKEN":
            chars = _token_chars(_payload(ev))
            if out and out[-1]["type"] == "TOKEN":
                out[-1]["count"] += 1
                out[-1]["chars"] += chars
            else:
                out.append({"type": "TOKEN", "stage": "", "count": 1, "chars": chars})
            continue
        out.append(_describe(ev))
    return out


async def _drain(center: ChatCenter, message: str, mode: str) -> list[StreamEvent]:
    events: list[StreamEvent] = []
    async for ev in center.stream_chat(
        message=message,
        history=[],
        mode=mode,
        student_profile={},
        user_id=0,
        conversation_id=None,
        style="standard",
        images=[],
    ):
        events.append(ev)
    return events


def _plan_view(plan) -> list[dict]:
    return [
        {"mode": t.mode, "intent": t.intent, "sequence": t.sequence}
        for t in plan.tasks
    ]


# ── 终态合同（异常/提前终止）测试替身 ──────────────────────────────
# 与 ai-service/tests/test_chat_center_stream_contract.py 的 _StubChatTaskDispatcher
# 同构：预置事件序列，可选在末尾抛错；`execute` 只 yield 事件、不触碰真实 LLM。


def _token(content: str) -> StreamEvent:
    """token helper：字符串包成 {"content": s}（对齐真实 _token_event）。"""
    return StreamEvent(type=StreamEventType.TOKEN, data={"content": content})


class _ProgDispatcher:
    """可编程 ChatTaskDispatcher 替身：预置事件序列或抛错。"""

    def __init__(self, events=None, *, error=None):
        self._events = list(events or [])
        self._error = error
        self.execute_calls: list = []

    async def execute(self, plan):
        self.execute_calls.append(plan)
        for ev in self._events:
            await asyncio.sleep(0)
            yield ev
        if self._error is not None:
            await asyncio.sleep(0)
            raise self._error


def _control_center(dispatcher: _ProgDispatcher) -> ChatCenter:
    """受控 ChatCenter：注入替身 dispatcher + 空分组抽取，隔离 LLM/DB。

    不传 use_mock_llm：self.dispatcher 非空 → _get_dispatcher() 原样返回，
    不会构造任何真实 Agent / Center，因此无需 API Key、无网络调用。
    """
    center = ChatCenter()
    center.dispatcher = dispatcher
    center._extract_knowledge_nodes = _stub_extract
    center._recommendation_timeout_sec = 1.0
    return center


# 4 条终态合同用例：缺 done 补发 / 多 done 收敛 / 管线异常转 error / 追问不误判。
TERMINATION_CASES: list[dict] = [
    {
        "case": "缺 done 补发",
        "events": [_token("前半段正文")],
        "error": None,
    },
    {
        "case": "多 done 收敛",
        "events": [
            _token("一"),
            done_event({"summary": "a"}),
            done_event({"summary": "b"}),
        ],
        "error": None,
    },
    {
        "case": "管线异常转 error",
        "events": [_token("前半段")],
        "error": RuntimeError("boom"),
    },
    {
        "case": "追问不误判空正文",
        "events": [
            inquiry_event("你想了解什么？"),
            done_event({"type": "inquiry", "is_clear": False}),
        ],
        "error": None,
    },
]


async def _drain_controlled(case: dict) -> list[StreamEvent]:
    dispatcher = _ProgDispatcher(events=case["events"], error=case["error"])
    center = _control_center(dispatcher)
    events: list[StreamEvent] = []
    async for ev in center.stream_chat(
        message="hi",
        history=[],
        mode="auto",
        student_profile={},
        user_id=0,
        conversation_id=None,
        style="standard",
        images=[],
    ):
        events.append(ev)
    return events


def _summarize_termination(events: list[StreamEvent]) -> dict:
    types = [e.type.name for e in events]
    done_events = [e for e in events if e.type.name == "DONE"]
    error_events = [e for e in events if e.type.name == "ERROR"]
    return {
        "type_sequence": " -> ".join(types),
        "last_is_done": types[-1] == "DONE" if types else False,
        "done_count": len(done_events),
        "error_count": len(error_events),
        "error_messages": [
            _payload(e).get("message", "") for e in error_events
        ],
        "done_keys": sorted(_payload(done_events[0]).keys()) if done_events else [],
    }


async def _run_termination_cases() -> list[dict]:
    records: list[dict] = []
    for case in TERMINATION_CASES:
        first = _summarize_termination(await _drain_controlled(case))
        second = _summarize_termination(await _drain_controlled(case))
        records.append(
            {
                "case": case["case"],
                **first,
                "deterministic": first == second,
            }
        )
    return records


async def _run_chain(chain: dict) -> dict:
    center = ChatCenter(use_mock_llm=True)
    center._extract_knowledge_nodes = _stub_extract
    center._recommendation_timeout_sec = 1.0

    plan = await center.route(message=chain["message"], mode=chain["mode"], context={})

    first = await _drain(center, chain["message"], chain["mode"])
    second = await _drain(center, chain["message"], chain["mode"])

    seq_a = _compress(first)
    seq_b = _compress(second)

    types = [e.type.name for e in first]
    done_events = [e for e in first if e.type.name == "DONE"]
    done_keys = sorted(_payload(done_events[0]).keys()) if done_events else []

    return {
        "chain": chain["chain"],
        "mode": chain["mode"],
        "message": chain["message"],
        "plan_tasks": _plan_view(plan),
        "plan_route": (plan.intent_meta or {}).get("route"),
        "plan_strategy": (plan.intent_meta or {}).get("strategy"),
        "events": seq_a,
        "type_sequence": " -> ".join(
            f"{e['type']}{'x'+str(e['count']) if e['type']=='TOKEN' else ''}"
            for e in seq_a
        ),
        "termination": {
            "last_is_done": types[-1] == "DONE" if types else False,
            "done_count": len(done_events),
            "error_count": sum(1 for t in types if t == "ERROR"),
            "done_keys": done_keys,
        },
        "deterministic": seq_a == seq_b,
    }


def _diff_paths(a: Any, b: Any, path: str = "") -> list[str]:
    """递归找出解析后两个 JSON 的结构差异路径（供 --verify 报错定位）。"""
    diffs: list[str] = []
    if type(a) is not type(b):
        diffs.append(f"{path}: 类型 {type(a).__name__} -> {type(b).__name__}")
        return diffs
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                diffs.append(f"{path}/{k}: 新增键")
            elif k not in b:
                diffs.append(f"{path}/{k}: 缺失键")
            else:
                diffs += _diff_paths(a[k], b[k], f"{path}/{k}")
    elif isinstance(a, list):
        if len(a) != len(b):
            diffs.append(f"{path}: 列表长度 {len(a)} -> {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diffs += _diff_paths(x, y, f"{path}[{i}]")
    elif a != b:
        diffs.append(f"{path}: {a!r} -> {b!r}")
    return diffs


def _emit(records: list[dict], termination: list[dict]) -> dict:
    return {"chains": records, "termination": termination}


async def _collect() -> dict:
    records = []
    for chain in CHAINS:
        records.append(await _run_chain(chain))
    termination = await _run_termination_cases()
    return _emit(records, termination)


async def verify() -> int:
    """--verify：重新生成契约并与基线文件比对（解析后精确 diff）。不一致返回非零。"""
    if not os.path.exists(OUT):
        print(f"[verify] 基线不存在: {OUT}")
        return 2
    with open(OUT, encoding="utf-8") as fh:
        baseline = json.load(fh)

    current = await _collect()
    if baseline == current:
        print(f"[verify] SSE 契约与基线一致（{OUT}）")
        return 0

    diffs = _diff_paths(baseline, current)
    print(f"[verify] SSE 契约已偏离基线：{len(diffs)} 处差异")
    for d in diffs[:50]:
        print(f"  {d}")
    if len(diffs) > 50:
        print(f"  ... 还有 {len(diffs) - 50} 处")
    return 1


async def main() -> None:
    records = []
    for chain in CHAINS:
        records.append(await _run_chain(chain))

    termination = await _run_termination_cases()

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(
            _emit(records, termination),
            fh,
            ensure_ascii=False,
            indent=2,
        )

    print(f"written: {OUT}\n")
    for r in records:
        term = r["termination"]
        print(f"[{r['chain']}] route={r['plan_route']} tasks={r['plan_tasks']}")
        print(f"  {r['type_sequence']}")
        print(
            f"  last_is_done={term['last_is_done']} done_count={term['done_count']} "
            f"error_count={term['error_count']} deterministic={r['deterministic']}"
        )
        print(f"  done_keys={term['done_keys']}\n")

    print("── 终态合同（异常/提前终止）──")
    for t in termination:
        print(
            f"[{t['case']}] last_is_done={t['last_is_done']} "
            f"done_count={t['done_count']} error_count={t['error_count']} "
            f"deterministic={t['deterministic']}"
        )
        print(f"  {t['type_sequence']}")
        if t["error_messages"]:
            print(f"  error_messages={t['error_messages']}")
    print()

    nondet = [r["chain"] for r in records if not r["deterministic"]]
    nondet += [t["case"] for t in termination if not t["deterministic"]]
    if nondet:
        print(f"非确定项: {nondet}")
    else:
        print("全部链路 + 终态合同两次运行一致（结构层面确定）。")


if "--verify" in sys.argv:
    sys.exit(asyncio.run(verify()))

asyncio.run(main())
