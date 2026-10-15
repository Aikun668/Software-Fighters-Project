"""T4-A 旁路对照探针（只读，不改路由行为）。

对 140 条 routing_cases 逐条走真实入口 ChatCenter.route()，产出：
  1. 与 T0 探针 probe_routing_snapshot 完全相同的 record 结构（gate_decide + entry），
     用同一算法算「旧行为指纹」——必须等于 T0 的 2624a51be09b9d5e，自证旁路不改执行。
  2. T4-A 三态旁路字段（semantic_state / route_source / semantic_called / ...）。

运行（Windows/中文控制台）：
    cd ai-service
    PYTHONUTF8=1 python ../docs/agent-engineering/routing-baseline/probe_t4a_sidecar.py
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
OUT = os.path.join(HERE, "routing_t4a_sidecar.jsonl")

# 与 probe_routing_snapshot.py 完全一致的构造（旁路默认 t4a_enabled=False）
_center_route = ChatCenter()
_gate = CapabilityGate()


def load_cases() -> list[dict]:
    with open(CASES, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def build_context(history: list[dict], message: str) -> dict:
    """与 probe_routing_snapshot.build_context 一致。"""
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


def entry_view(plan) -> dict:
    """与 probe_routing_snapshot.entry_view 完全一致。"""
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


def t4a_view(plan) -> dict:
    meta = dict(plan.intent_meta or {})
    return {
        "semantic_state": meta.get("semantic_state"),
        "route_source": meta.get("route_source"),
        "semantic_called": meta.get("semantic_called"),
        "semantic_latency_ms": meta.get("semantic_latency_ms"),
        "semantic_error": meta.get("semantic_error"),
        "semantic_intents": meta.get("semantic_intents"),
        "semantic_is_clear": meta.get("semantic_is_clear"),
    }


def fingerprint(records: list[dict]) -> str:
    blob = json.dumps(records, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


async def main() -> None:
    cases = load_cases()
    sidecar: list[dict] = []
    old_records: list[dict] = []
    for case in cases:
        message = case.get("message", "")
        mode = case.get("mode", "auto")
        context = build_context(case.get("history") or [], message)
        plan = await _center_route.route(message=message, mode=mode, context=context)

        # 旧行为 record：与 T0 探针同结构（含 gate_decide + entry + deterministic）
        entry = entry_view(plan)
        old_records.append({
            "case_id": case["case_id"],
            "category": case["category"],
            "source_type": case.get("source_type"),
            "mode": mode,
            "message": message,
            "gate_decide": gate_view(message, mode),
            "entry": entry,
            "error": None,
            "deterministic": True,
        })
        sidecar.append({
            "case_id": case["case_id"],
            "category": case["category"],
            "message": message,
            "mode": mode,
            "old": entry,
            "t4a": t4a_view(plan),
        })

    with open(OUT, "w", encoding="utf-8") as fh:
        for rec in sidecar:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    fp = fingerprint(old_records)
    print(f"written: {OUT}")
    print(f"cases: {len(sidecar)}")
    print(f"OLD fingerprint: {fp}   (T0 期望 2624a51be09b9d5e)")

    from collections import Counter

    states = Counter(r["t4a"]["semantic_state"] for r in sidecar)
    sources = Counter(r["t4a"]["route_source"] for r in sidecar)
    called = sum(1 for r in sidecar if r["t4a"]["semantic_called"])
    print("\n三态分布:")
    for k, v in sorted(states.items(), key=lambda x: -x[1]):
        print(f"  {v:3}  {k}")
    print("\nroute_source 分布:")
    for k, v in sorted(sources.items(), key=lambda x: -x[1]):
        print(f"  {v:3}  {k}")
    print(f"\nsemantic_called={called}")


asyncio.run(main())
