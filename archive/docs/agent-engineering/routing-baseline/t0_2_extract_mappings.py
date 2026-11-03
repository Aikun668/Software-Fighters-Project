"""T0.2 · 冻结重构前的能力/意图映射表（只读抽取）。

[只读] 只 import 生产模块的**模块级/类级常量**，不调用任何路由/执行入口，
不写库、不改代码、不合并表。输出的 `legacy_mappings.json` 是重构前真源的
机器可读快照，供 T1 收口后逐字段 diff。

运行（Windows/中文控制台）：
    cd ai-service
    PYTHONUTF8=1 python ../docs/agent-engineering/routing-baseline/t0_2_extract_mappings.py
"""
import hashlib
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
AI_SERVICE = os.path.abspath(os.path.join(HERE, "..", "..", "..", "ai-service"))
sys.path.insert(0, AI_SERVICE)

from app.services.intent_extractor import (  # noqa: E402
    INTENT_CENTER_MAP,
    INTENT_REGISTRY,
    _CENTER_EXECUTION_ORDER,
    _INTENT_PRIORITY,
    _MUTEX_GROUPS,
)
from app.services.capability_gate import (  # noqa: E402
    _CAPABILITY_RULES,
    _MODE_TO_KIND,
)
from app.centers.router_agent import RouterAgent  # noqa: E402
from app.centers.chat_center import _KIND_TO_CENTER  # noqa: E402
from app.centers.chat_task_dispatcher import ChatTaskDispatcher  # noqa: E402

# 与 T0.1 冻结指纹一致：这些文件承载全部映射真源
MAPPING_SOURCE_FILES = [
    "app/services/intent_extractor.py",
    "app/services/capability_gate.py",
    "app/centers/router_agent.py",
    "app/centers/chat_center.py",
    "app/centers/chat_task_dispatcher.py",
]


def sha256_of(rel_path: str) -> str:
    with open(os.path.join(AI_SERVICE, rel_path), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def build_snapshot() -> dict:
    registered = [d.intent for d in INTENT_REGISTRY]

    # 组装 §二「规范化真源表」所需的每意图一行（不改生产代码，仅只读投影）
    intent_rows = []
    for d in INTENT_REGISTRY:
        center = INTENT_CENTER_MAP.get(d.intent)
        intent_rows.append({
            "intent": d.intent,
            "center": center,
            "order": _CENTER_EXECUTION_ORDER.get(center),
            "on_token": center in ChatTaskDispatcher._ON_TOKEN_MODES,
            "confidence_multiplier": d.confidence,
            "keywords": list(d.keywords),
            "exclusive_keywords": list(d.exclusive_keywords),
            "keywords_count": len(d.keywords),
        })
    # 未注册但登记的 center（如 unknown）
    center_only = [
        {"intent": k, "center": v, "order": _CENTER_EXECUTION_ORDER.get(v)}
        for k, v in INTENT_CENTER_MAP.items()
        if k not in registered
    ]

    return {
        "t0_2_version": 1,
        "ai_service_root": AI_SERVICE,
        "source_sha256": {f: sha256_of(f) for f in MAPPING_SOURCE_FILES},
        "tables": {
            "INTENT_REGISTRY": [d.intent for d in INTENT_REGISTRY],
            "INTENT_CENTER_MAP": dict(INTENT_CENTER_MAP),
            "_CENTER_EXECUTION_ORDER": dict(_CENTER_EXECUTION_ORDER),
            "RouterAgent.MODE_TO_INTENT": dict(RouterAgent.MODE_TO_INTENT),
            "chat_center._KIND_TO_CENTER": dict(_KIND_TO_CENTER),
            "chat_task_dispatcher._ON_TOKEN_MODES": sorted(
                ChatTaskDispatcher._ON_TOKEN_MODES
            ),
            "capability_gate._MODE_TO_KIND": {
                k: v.value for k, v in _MODE_TO_KIND.items()
            },
            "capability_gate._CAPABILITY_RULES": [
                {"kind": k.value, "rule": r, "pattern": p.pattern}
                for k, r, p in _CAPABILITY_RULES
            ],
            "intent_extractor._MUTEX_GROUPS": [sorted(g) for g in _MUTEX_GROUPS],
            "intent_extractor._INTENT_PRIORITY": dict(_INTENT_PRIORITY),
        },
        "per_intent_projection": intent_rows,
        "center_only_entries": center_only,
    }


def main() -> None:
    snap = build_snapshot()
    out_path = os.path.join(HERE, "legacy_mappings.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(snap, fh, ensure_ascii=False, indent=2, sort_keys=False)

    print(f"written: {out_path}")
    print(f"registered intents: {len(snap['tables']['INTENT_REGISTRY'])}")
    print(f"INTENT_CENTER_MAP entries: {len(snap['tables']['INTENT_CENTER_MAP'])}")
    print(f"capability rules: {len(snap['tables']['capability_gate._CAPABILITY_RULES'])}")
    print("\nsource fingerprints:")
    for f, h in snap["source_sha256"].items():
        print(f"  {h}  {f}")
    print("\nper-intent projection:")
    for row in snap["per_intent_projection"]:
        print(
            f"  {row['intent']:16} center={row['center']:13} "
            f"order={row['order']} on_token={row['on_token']} "
            f"conf={row['confidence_multiplier']}"
        )


if __name__ == "__main__":
    main()
