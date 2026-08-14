"""
并行轰炸测试 + LLM 裁判 — 主入口

用法:
  python tests/bombardment/run.py              # 跑全部场景
  python tests/bombardment/run.py --dry        # 只跑请求，不调裁判

流程:
  1. 并行 HTTP 请求轰炸 (ThreadPoolExecutor, 并发数=MAX_WORKERS)
  2. 收集 SSE 流式响应，提取完整文本
  3. 并行 LLM 裁判评审 (每场景独立 rubric)
  4. 直接输出量化结果
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.bombardment.scenarios import SCENARIOS
from tests.bombardment.judge import run_judges_parallel

MAX_WORKERS = 3  # 并行轰炸并发数（受 LLM API 并发限制）
REQUEST_TIMEOUT = 120  # 单个请求超时


# ═══════════════════════ SSE 解析 ═══════════════════════

def _extract_sse_response(sse_body: str) -> str:
    """从 SSE 流提取完整回复文本。"""
    parts = []
    for line in sse_body.split("\n"):
        if line.startswith("data: "):
            data = line[6:]
            try:
                event = json.loads(data)
                t = event.get("type", "")
                if t == "content":
                    nested = event.get("data", {})
                    if isinstance(nested, dict):
                        r = nested.get("response", "")
                        if isinstance(r, str):
                            parts.append(r)
                elif t == "token":
                    c = event.get("content", "")
                    if isinstance(c, str):
                        parts.append(c)
                elif t == "error":
                    return f"[ERROR] {event.get('content', 'unknown')}"
            except json.JSONDecodeError:
                continue
    return "".join(parts).strip()


# ═══════════════════════ 单请求执行 ═══════════════════════

def _send_one(scenario: dict) -> dict:
    """发送单个请求，返回 (scenario, response_text, elapsed, status)。"""
    req = scenario["request"]
    url = req["url"]
    body = req["body"]

    t0 = time.time()
    try:
        r = requests.post(url, json=body, timeout=REQUEST_TIMEOUT)
        elapsed = time.time() - t0
        status = r.status_code

        if status == 200:
            text = _extract_sse_response(r.text)
            if not text:
                # 可能不是 SSE：尝试直接 JSON
                try:
                    data = r.json()
                    text = json.dumps(data, ensure_ascii=False, indent=2)
                except Exception:
                    text = r.text[:3000]
        else:
            text = f"[HTTP {status}] {r.text[:500]}"

    except (requests.exceptions.Timeout, requests.Timeout):
        elapsed = time.time() - t0
        status = -1
        text = "[TIMEOUT] 请求超时"
    except Exception as e:
        elapsed = time.time() - t0
        status = -2
        text = f"[EXCEPTION] {e}"

    return {
        "id": scenario["id"],
        "category": scenario["category"],
        "description": scenario["description"],
        "status": status,
        "elapsed": round(elapsed, 2),
        "response": text,
        "response_len": len(text),
    }


# ═══════════════════════ 并行轰炸 ═══════════════════════

def run_bombardment(scenarios: list[dict]) -> list[dict]:
    """并行发送所有请求，返回原始结果列表。"""
    n = len(scenarios)
    results = [None] * n

    print(f"\n{'='*80}")
    print(f"  并行轰炸测试 — {n} 个场景 — {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*80}\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_send_one, s): i for i, s in enumerate(scenarios)}
        for f in as_completed(futures):
            result = f.result()
            idx = futures[f]  # original index, not the result's id
            # Re-sort by scenario order
            for j, s in enumerate(scenarios):
                if s["id"] == result["id"]:
                    results[j] = result
                    break

            icon = "OK" if result["status"] == 200 else "FAIL"
            print(f"  [{icon}] {result['id']:<30s} "
                  f"status={result['status']} "
                  f"len={result['response_len']:<6d} "
                  f"{result['elapsed']:.1f}s")

    return results


# ═══════════════════════ 报告生成 ═══════════════════════

def generate_summary(raw_results: list[dict]) -> str:
    """生成汇总输出。"""
    lines = []
    lines.append(f"\n{'='*80}")
    lines.append("  测试结果汇总")
    lines.append(f"{'='*80}")

    # ── 响应概览 ──
    lines.append(f"\n{'─'*80}")
    lines.append("  响应概览")
    lines.append(f"{'─'*80}")
    lines.append(f"  {'ID':<28s} {'类别':<10s} {'状态':<6s} {'耗时':<8s} {'长度':<6s}")
    ok_count = 0
    for r in raw_results:
        sid = r["id"]
        cat = r["category"]
        status = "OK" if r["status"] == 200 else f"ERR({r['status']})"
        elapsed = f"{r['elapsed']:.1f}s"
        length = r["response_len"]
        lines.append(f"  {sid:<28s} {cat:<10s} {status:<6s} {elapsed:<8s} {length:<6d}")
        if r["status"] == 200:
            ok_count += 1

    # ── 性能 ──
    valid = [r for r in raw_results if r["status"] == 200]
    if valid:
        times = [r["elapsed"] for r in valid]
        lens = [r["response_len"] for r in valid]
        lines.append(f"\n  成功率: {ok_count}/{len(raw_results)} ({ok_count/len(raw_results)*100:.0f}%)")
        lines.append(f"  响应时间: avg={sum(times)/len(times):.1f}s  min={min(times):.1f}s  max={max(times):.1f}s")
        lines.append(f"  回复长度: avg={int(sum(lens)/len(lens))} 字符")

    # ── 裁判评分 ──
    judged = [r for r in raw_results if "judge_score" in r]
    if judged:
        lines.append(f"\n{'─'*80}")
        lines.append("  LLM 裁判评分")
        lines.append(f"{'─'*80}")
        lines.append(f"  {'场景':<28s} {'总分':<6s} {'判定':<6s} {'各维度'}")

        totals = []
        pass_count = 0
        for r in judged:
            js = r.get("judge_score", {})
            total = js.get("total", 0)
            totals.append(total)
            threshold = r.get("pass_threshold", 0.6)
            passed = total >= threshold
            if passed:
                pass_count += 1
            flag = "PASS" if passed else "FAIL"
            scores_str = "  ".join(
                f"{k}:{v:.2f}" for k, v in js.get("scores", {}).items()
            )
            lines.append(f"  {r['id']:<28s} {total:.2f}   {flag:<6s} {scores_str}")

        avg_score = sum(totals) / len(totals) if totals else 0
        lines.append(f"\n  裁判平均分: {avg_score:.2f}  |  通过率: {pass_count}/{len(judged)} ({pass_count/len(judged)*100:.0f}%)")

        # ASCII 分布图
        if len(totals) >= 3:
            lines.append(f"\n  得分分布:")
            lines.append(_ascii_histogram(totals, bins=5))

    # ── 关键发现 ──
    lines.append(f"\n{'─'*80}")
    lines.append("  关键发现")
    lines.append(f"{'─'*80}")
    fails = [r for r in raw_results if r["status"] != 200]
    if fails:
        lines.append(f"  FAIL: {len(fails)} 个请求失败 — {', '.join(r['id'] for r in fails)}")
    low_scores = [r for r in judged if r.get("judge_score", {}).get("total", 0) < r.get("pass_threshold", 0.6)]
    if low_scores:
        for r in low_scores:
            lines.append(f"  LOW: {r['id']} (total={r['judge_score']['total']:.2f}) — {r['judge_score'].get('comment', '')}")
    if not fails and not low_scores:
        lines.append("  全部通过，未发现显著问题。")

    lines.append(f"\n{'='*80}\n")
    return "\n".join(lines)


def _ascii_histogram(values: list[float], bins: int = 5) -> str:
    """ASCII 柱状图。"""
    if not values:
        return ""
    lo, hi = 0.0, 1.0
    step = (hi - lo) / bins
    buckets = [0] * bins
    for v in values:
        idx = min(int((v - lo) / step), bins - 1)
        buckets[idx] += 1

    lines = []
    bar_max = 30
    max_count = max(buckets) if max(buckets) > 0 else 1
    for i in range(bins):
        low = lo + i * step
        high = lo + (i + 1) * step
        bar = "█" * int(buckets[i] / max_count * bar_max)
        lines.append(f"  {low:.1f}-{high:.1f}  {bar}  {buckets[i]}")
    return "\n".join(lines)


# ═══════════════════════ 主流程 ═══════════════════════

def main():
    dry_run = "--dry" in sys.argv

    # 1. 并行轰炸
    raw_results = run_bombardment(SCENARIOS)

    if dry_run:
        print("\n--dry 模式，跳过 LLM 裁判。")
        return

    # 2. LLM 裁判评审
    print(f"\n{'='*80}")
    print(f"  LLM 裁判评审")
    print(f"{'='*80}\n")

    scenarios_with_responses = [
        (SCENARIOS[i], r["response"])
        for i, r in enumerate(raw_results)
        if r["status"] == 200 and r["response"]
    ]

    if not scenarios_with_responses:
        print("没有可评审的成功响应，跳过裁判。")
        return

    judge_results = run_judges_parallel(scenarios_with_responses)

    # 3. 合并裁判结果
    for jr in judge_results:
        sid = jr.get("scenario_id", "")
        for r in raw_results:
            if r["id"] == sid:
                r["judge_score"] = {
                    "scores": jr.get("scores", {}),
                    "total": jr.get("total", 0),
                    "verdict": jr.get("verdict", "ERROR"),
                    "comment": jr.get("comment", ""),
                }
                r["pass_threshold"] = jr.get("pass_threshold", 0.6)
                break

        print(f"  [{jr.get('verdict', '?')}] {sid:<30s} "
              f"total={jr.get('total', 0):.2f}  "
              f"{jr.get('comment', '')[:80]}")

    # 4. 直接输出汇总
    print(generate_summary(raw_results))


if __name__ == "__main__":
    main()
