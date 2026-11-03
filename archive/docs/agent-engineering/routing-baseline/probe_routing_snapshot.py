"""T0.3 · 冻结重构前的路由行为快照（只读）。

[只读] 复用既有 `routing_cases.jsonl`（140 条），逐条调用**真实路由入口**
`ChatCenter.route()`——它内部按真实顺序走 CapabilityGate(一级) →
RouterAgent(二级) → gate 权威兜底。同时独立记录 `CapabilityGate.decide()` 的
原始判定，便于把「门判定」与「入口结果」分开对账。

不触发任何生成任务、不写库、不改代码；不做事后 Gold-Label 精度打分
（那属下一阶段）。只记录**重构前的真实行为**。

确定性：`route()` 只用 message/mode，`context`/`student_profile` 不参与判定；
输出剔除随机 `trace_id`。每条跑两次，逐字段比对，不一致即报 MISMATCH。

运行（Windows/中文控制台）：
    cd ai-service
    PYTHONUTF8=1 python ../docs/agent-engineering/routing-baseline/probe_routing_snapshot.py
"""
import asyncio
import hashlib
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
AI_SERVICE = os.path.abspath(os.path.join(HERE, "..", "..", "..", "ai-service"))
sys.path.insert(0, AI_SERVICE)

from app.centers.chat_center import ChatCenter  # noqa: E402
from app.services.capability_gate import CapabilityGate  # noqa: E402

CASES = os.path.join(HERE, "routing_cases.jsonl")
OUT = os.path.join(HERE, "routing_snapshot.jsonl")

_center_route = ChatCenter()  # route() 只惰性构造 gate+router，无 LLM/IO
_gate = CapabilityGate()


def load_cases() -> list[dict]:
    with open(CASES, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def build_context(history: list[dict], message: str) -> dict:
    """复刻 ChatCenter.stream_chat 的真实 context 组装（internal_api/chat.py）。"""
    messages = list(history or []) + [{"role": "user", "content": message}]
    return {
        "messages": messages,
        "style": "standard",
        "images": [],
        "user_id": 0,
        "conversation_id": None,
    }


def gate_view(message: str, mode: str) -> dict:
    d = _gate.decide(message=message, mode=mode)
    return {"kind": d.kind.value, "reason": d.reason, "confidence": d.confidence}


async def entry_view(message: str, mode: str, context: dict) -> dict:
    plan = await _center_route.route(message=message, mode=mode, context=context)
    meta = dict(plan.intent_meta or {})
    return {
        "strategy": meta.get("strategy"),
        "route": meta.get("route"),
        "route_reason": meta.get("route_reason"),
        "is_clear": plan.is_clear,
        "needs_confirmation": plan.needs_confirmation,
        "inquiry_question": plan.inquiry_question or None,
        "max_intents": plan.max_intents,
        "tasks": [
            {
                "mode": t.mode,
                "intent": t.intent,
                "sequence": t.sequence,
                "confidence": round(t.confidence, 6),
                "params": t.params,
            }
            for t in plan.tasks
        ],
        "intents": [t.intent for t in plan.tasks],
        "modes": [t.mode for t in plan.tasks],
    }


async def run_case(case: dict) -> dict:
    message = case.get("message", "")
    mode = case.get("mode", "auto")
    context = build_context(case.get("history") or [], message)

    record = {
        "case_id": case["case_id"],
        "category": case["category"],
        "source_type": case.get("source_type"),
        "mode": mode,
        "message": message,
        "gate_decide": gate_view(message, mode),
        "entry": None,
        "error": None,
    }
    try:
        first = await entry_view(message, mode, context)
        second = await entry_view(message, mode, context)
        record["entry"] = first
        record["deterministic"] = first == second
    except Exception as exc:  # 记录异常本身，不伪造结果
        record["error"] = {"type": type(exc).__name__, "message": str(exc)}
        record["deterministic"] = None
    return record


def fingerprint(records: list[dict]) -> str:
    blob = json.dumps(records, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


async def main() -> None:
    cases = load_cases()
    records = []
    for case in cases:
        records.append(await run_case(case))

    with open(OUT, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    errs = [r for r in records if r["error"]]
    nondet = [r for r in records if r.get("deterministic") is False]

    print(f"written: {OUT}")
    print(f"cases: {len(records)}  errors: {len(errs)}  "
          f"nondeterministic: {len(nondet)}  fingerprint: {fingerprint(records)}")
    print("\nstrategy 分布:")
    dist: dict[str, int] = {}
    for r in records:
        key = ("ERROR" if r["error"]
               else f"{r['entry']['strategy']}/{r['entry']['route']}")
        dist[key] = dist.get(key, 0) + 1
    for k, v in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"  {v:3}  {k}")

    if errs:
        print("\n异常用例:")
        for r in errs:
            print(f"  {r['case_id']} {r['error']}")
    if nondet:
        print("\n非确定用例:")
        for r in nondet:
            print(f"  {r['case_id']}")


asyncio.run(main())
