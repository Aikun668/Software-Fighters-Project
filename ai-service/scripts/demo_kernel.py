"""内核演示入口 —— 一条命令跑通「一句话 → 多 Agent 编排 → 流式结果」。

这是《简历沉淀总计划》**阶段 1** 的交付物：证明 Python Agent 内核
**不依赖 Java / 前端 / MySQL / Redis / MinIO**，一条命令即可完整跑通。

依赖面：只走 ASGI 进程内调用（`internal_api.router`），**不启动任何服务器**。
服务入口 `internal_api` 与生产 `python main.py` 完全同源，因此演示结果
与线上链路一致（不是另造一条捷径）。

用法（在 ai-service 目录下执行）：

    # 默认：mock 引擎 + 资源生成场景，离线可跑，秒级返回
    python scripts/demo_kernel.py

    # 指定场景 / 引擎
    python scripts/demo_kernel.py --scenario tutor --mode real

    # 复现性验证：连跑 2 次，比对指纹是否一致
    python scripts/demo_kernel.py --repeat 2

    # 落一份原始帧存证
    python scripts/demo_kernel.py --json-out temp_file/evidence/kernel-demo.json

场景说明（为什么默认不是问答）：问答走 TutorAgent 的 RAG 链路，首次运行需
加载 `sentence-transformers` embedding 模型，**冷启动可长达分钟级**（还会在
无网环境下等 HF 检查更新）。资源生成链路不碰 embedding，因此作为默认场景。
二者都是真实链路，只是耗时特征不同。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time

# ── 必须在 import app.* / internal_api 之前决定引擎开关 ──────────────
# 工厂在**构造 Agent 时**读这个变量，晚于此处的赋值不会生效。
_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVICE_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _SERVICE_ROOT not in sys.path:
    sys.path.insert(0, _SERVICE_ROOT)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(_SERVICE_ROOT, ".env"))


# ═══════════════════════════════════════════════════════════════════
# 固定演示场景（保证每次可复现）
# ═══════════════════════════════════════════════════════════════════

SCENARIOS: dict[str, dict] = {
    "resource": {
        "label": "给「注意力机制」生成一套学习资源",
        "endpoint": "/internal/api/chat",
        "payload": {"message": "给注意力机制生成一套学习资源", "mode": "auto"},
        "note": "意图门控 → 资源路由 → 生成 → 质量门 → 流式输出；不加载 embedding",
    },
    "resource_direct": {
        "label": "资源域直连：「注意力机制」",
        "endpoint": "/internal/resources/generate",
        "payload": {"topic": "注意力机制"},
        "note": "绕过意图门控，直接打资源域 Center；质量门终态在 done 帧里最完整",
    },
    "tutor": {
        "label": "问答「什么是注意力机制？」",
        "endpoint": "/internal/api/chat",
        "payload": {"message": "什么是注意力机制？", "mode": "auto"},
        "note": "TutorAgent RAG 链路（retrieve → respond）；首次运行需加载 embedding，冷启动慢",
    },
}

# 进度帧里这几类值得高亮（编排骨架）
_HIGHLIGHT = {"center_start", "center_end", "stage_start", "stage_end", "progress", "error"}


# ═══════════════════════════════════════════════════════════════════
# SSE 解析
# ═══════════════════════════════════════════════════════════════════

def _frames_of(text: str) -> list[dict]:
    """把 SSE 文本解析成事件字典列表（忽略 `:heartbeat` 等注释行）。"""
    out: list[dict] = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        try:
            out.append(json.loads(line[len("data: "):]))
        except ValueError:
            out.append({"type": "__unparsable__", "raw": line})
    return out


def _fingerprint(frames: list[dict]) -> str:
    """稳定指纹：只取跨环境可复现的字段，用于「每次运行结果一致」的验证。

    刻意排除时间/耗时/会话 ID 等环境相关字段（与 `acceptance/harness/
    chat_progress_frames.py` 同法），否则 mock 下也会每次不同。
    """
    parts: list[str] = []
    for frame in frames:
        kind = frame.get("type")
        data = frame.get("data") or {}
        if kind == "token":
            parts.append(f"token:{frame.get('content')}")
        elif kind == "progress":
            parts.append(f"progress:{frame.get('stage')}:{data.get('phase')}")
        elif kind in ("stage_start", "stage_end", "center_start", "center_end"):
            parts.append(f"{kind}:{frame.get('stage')}:{frame.get('message')}")
        elif kind == "content":
            blocks = data.get("content_blocks") or []
            headings = [str(b.get("heading") or "") for b in blocks if isinstance(b, dict)]
            parts.append(f"content:{data.get('type')}:{len(blocks)}:{'|'.join(headings)}")
        elif kind == "done":
            inner = data if isinstance(data, dict) else {}
            results = inner.get("results") or []
            agents = [str(r.get("agent") or "") for r in results if isinstance(r, dict)]
            parts.append(
                f"done:review={inner.get('review_status')}:"
                f"final={inner.get('final_status')}:agents={','.join(agents)}"
            )
        elif kind == "error":
            parts.append(f"error:{frame.get('content') or frame.get('message')}")
        else:
            parts.append(str(kind))
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════
# 单次运行
# ═══════════════════════════════════════════════════════════════════

async def run_once(
    client,
    scenario: dict,
    *,
    verbose: bool = True,
) -> dict:
    """跑一个场景，边收边渲染编排过程，返回结构化结果。"""
    endpoint = scenario["endpoint"]
    payload = {
        "user_id": 1,
        "student_profile": {},
        **scenario["payload"],
    }
    if endpoint.endswith("/api/chat"):
        payload.setdefault("messages", [])

    frames: list[dict] = []
    timeline: list[tuple[float, str]] = []
    started = time.perf_counter()

    async with client.stream("POST", endpoint, json=payload) as response:
        status = response.status_code
        if verbose:
            print(f"  HTTP {status}  {endpoint}")
            print()
            print("  ── 编排过程 ──────────────────────────────────────────")

        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            try:
                frame = json.loads(line[len("data: "):])
            except ValueError:
                continue
            frames.append(frame)

            elapsed = time.perf_counter() - started
            kind = frame.get("type")
            if verbose and kind in _HIGHLIGHT:
                stage = frame.get("stage") or ""
                phase = (frame.get("data") or {}).get("phase") or ""
                message = frame.get("message") or ""
                if kind == "progress" and not message:
                    message = (frame.get("data") or {}).get("content") or ""
                tag = f"{stage}{('/' + phase) if phase else ''}"
                # 进度帧成对出现，用缩进体现层级
                indent = "    " if kind == "progress" else "  "
                print(f"  [{elapsed:6.2f}s]{indent}{kind:<13} {tag:<22} {message}")
                timeline.append((elapsed, f"{kind}:{tag}"))

    total_ms = (time.perf_counter() - started) * 1000
    return {"frames": frames, "status": status, "total_ms": total_ms, "timeline": timeline}


def _summarise(frames: list[dict]) -> dict:
    """从帧集合里提取演示要点：编排骨架 + 质量门 + 终态。"""
    types: dict[str, int] = {}
    for frame in frames:
        types[frame.get("type")] = types.get(frame.get("type"), 0) + 1

    # 编排阶段：progress 帧带 stage；资源域直连场景只有 stage_start/stage_end，
    # 因此两类都要看，否则会出现「编排阶段：(无)」的误导性输出。
    stages: list[str] = []
    for frame in frames:
        if frame.get("type") in ("progress", "stage_start"):
            stage = frame.get("stage")
            if stage and stage not in stages:
                stages.append(stage)

    content: dict = {}
    for frame in frames:
        if frame.get("type") == "content":
            content = frame.get("data") or {}

    done: dict = {}
    for frame in frames:
        if frame.get("type") == "done":
            done = frame.get("data") or {}

    blocks = content.get("content_blocks") or done.get("content_blocks") or []
    tokens = "".join(
        str(f.get("content") or "") for f in frames if f.get("type") == "token"
    )
    errors = [
        frame.get("content") or frame.get("message")
        for frame in frames
        if frame.get("type") == "error"
    ]
    agents = [
        str(r.get("agent") or "")
        for r in (done.get("results") or [])
        if isinstance(r, dict)
    ]

    return {
        "types": types,
        "stages": stages,
        "blocks": blocks,
        "tokens": tokens,
        "errors": errors,
        "agents": agents,
        "review_status": content.get("review_status") or done.get("review_status"),
        "final_status": content.get("final_status") or done.get("final_status"),
        "response": content.get("response") or done.get("summary") or "",
    }


# ═══════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════

async def _main_async(args: argparse.Namespace) -> int:
    names = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    for name in names:
        if name not in SCENARIOS:
            print(f"[!] 未知场景 {name!r}，可选：{', '.join(SCENARIOS)}", file=sys.stderr)
            return 2

    use_mock = args.mode == "mock"
    os.environ["AI_SERVICE_MOCK_LLM"] = "1" if use_mock else "0"

    from fastapi import FastAPI  # noqa: E402
    from httpx import ASGITransport, AsyncClient  # noqa: E402

    from internal_api import router  # noqa: E402

    app = FastAPI()
    app.include_router(router)

    engine = "mock（离线，不调用真实模型）" if use_mock else "real（真实模型调用）"
    print("=" * 74)
    print("  Python Agent 内核演示 · 一句话 → 多 Agent 编排 → 流式结果")
    print(f"  引擎: {engine}")
    print(f"  依赖: 无 Java / 无前端 / 无 MySQL / 无 Redis / 无 MinIO")
    print("=" * 74)

    reports: list[dict] = []
    # 指纹按**场景**分组：不同场景本就产出不同事件流，混在一起比会得出
    # 「有 N 种不同指纹」的错误结论。复现性只在同一场景的多次运行之间成立。
    digests_by_scenario: dict[str, list[str]] = {name: [] for name in names}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://kernel-demo",
        timeout=args.timeout,
    ) as client:
        for name in names:
            scenario = SCENARIOS[name]
            print()
            print(f"### 场景 {name}：{scenario['label']}")
            print(f"    端点 {scenario['endpoint']}    {scenario['note']}")

            for round_no in range(1, args.repeat + 1):
                if args.repeat > 1:
                    print()
                    print(f"  ── 第 {round_no}/{args.repeat} 次 ──")
                result = await run_once(client, scenario, verbose=True)
                summary = _summarise(result["frames"])
                digest = hashlib.sha256(
                    _fingerprint(result["frames"]).encode("utf-8")
                ).hexdigest()
                digests_by_scenario[name].append(digest)

                print()
                print("  ── 结果 ──────────────────────────────────────────────")
                print(
                    f"    帧统计   : {result['frames'].__len__()} 帧  "
                    f"{summary['types']}"
                )
                print(f"    编排阶段 : {' → '.join(summary['stages']) or '(无)'}")
                if summary["agents"]:
                    print(f"    参与 Agent: {', '.join(summary['agents'])}")
                status_bits = []
                if summary["review_status"]:
                    status_bits.append(f"质量门={summary['review_status']}")
                if summary["final_status"]:
                    status_bits.append(f"终态={summary['final_status']}")
                if status_bits:
                    print(f"    质量门   : {'  '.join(status_bits)}")
                if summary["tokens"]:
                    print(f"    流式正文 : {len(summary['tokens'])} 字")
                    print(f"      {summary['tokens'][:200]}")
                if summary["response"]:
                    print(f"    摘要     : {summary['response']}")
                if summary["blocks"]:
                    print(f"    内容块   : {len(summary['blocks'])} 个")
                    for block in summary["blocks"]:
                        if isinstance(block, dict):
                            print(
                                f"      - [{block.get('type')}] "
                                f"{str(block.get('heading') or '')[:58]}"
                            )
                if summary["errors"]:
                    print(f"    [!] 错误帧: {summary['errors']}")
                print(f"    耗时     : {result['total_ms']:.0f} ms")
                print(f"    指纹     : sha256={digest[:16]}…")

                reports.append(
                    {
                        "scenario": name,
                        "round": round_no,
                        "status": result["status"],
                        "total_ms": round(result["total_ms"], 1),
                        "frame_types": summary["types"],
                        "stages": summary["stages"],
                        "agents": summary["agents"],
                        "review_status": summary["review_status"],
                        "final_status": summary["final_status"],
                        "block_count": len(summary["blocks"]),
                        "sha256": digest,
                    }
                )

                if args.json_out:
                    path = os.path.abspath(args.json_out)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "w", encoding="utf-8") as handle:
                        json.dump(
                            {
                                "mode": args.mode,
                                "scenario": name,
                                "round": round_no,
                                "report": reports[-1],
                                "frames": result["frames"],
                            },
                            handle,
                            ensure_ascii=False,
                            indent=2,
                        )
                    print(f"    存证     : {path}")

    # ── 复现性结论（--repeat > 1 时有意义）──
    print()
    print("=" * 74)
    if args.repeat > 1:
        all_same = True
        for name in names:
            unique = sorted(set(digests_by_scenario[name]))
            if len(unique) == 1:
                print(
                    f"  ✅ {name:<16} {len(digests_by_scenario[name])} 次运行指纹一致"
                    f"（{unique[0][:16]}…）"
                )
            else:
                all_same = False
                print(f"  ⚠️ {name:<16} {len(digests_by_scenario[name])} 次运行出现 "
                      f"{len(unique)} 种指纹")
                for d in unique:
                    print(f"       {d[:24]}…")
        print()
        if all_same:
            print("  ✅ 复现性：每个场景的多次运行均逐帧一致（可复现）")
        else:
            print("  ⚠️ 复现性：存在场景多次运行结果不一致，需要排查")
    else:
        print("  提示：加 --repeat 2 可验证「同一场景每次运行结果一致」")
    print("=" * 74)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Python Agent 内核演示：一句话 → 多 Agent 编排 → 流式结果",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--scenario",
        default="resource",
        choices=[*SCENARIOS, "all"],
        help="演示场景（默认 resource：给「注意力机制」生成学习资源）",
    )
    parser.add_argument(
        "--mode",
        default="mock",
        choices=["mock", "real"],
        help="引擎：mock=离线不调模型（默认）；real=真实模型，需 .env 里的 Key",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        metavar="N",
        help="重复次数，用于验证结果可复现（默认 1）",
    )
    parser.add_argument(
        "--json-out",
        default="",
        metavar="PATH",
        help="把原始帧存成 JSON（存证用）",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="单次请求超时秒数（默认 600；问答场景冷启动可能较久）",
    )
    args = parser.parse_args()

    if args.repeat < 1:
        print("[!] --repeat 必须 >= 1", file=sys.stderr)
        return 2

    if args.mode == "real":
        key = (
            os.getenv("DEEPSEEK_API_KEY", "")
            or os.getenv("MINIMAX_API_KEY", "")
        ).strip()
        if not key:
            print(
                "[!] --mode real 需要真实 Key：请在 ai-service/.env 里配置\n"
                "    DEEPSEEK_API_KEY（或 MINIMAX_API_KEY），或改用默认的 --mode mock。",
                file=sys.stderr,
            )
            return 2

    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
