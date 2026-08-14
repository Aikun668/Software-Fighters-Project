"""
P0 核心用户链路测试 — 主入口

用法:
  python tests/bombardment/run_p0.py              # 完整测试（轰炸 + 裁判）
  python tests/bombardment/run_p0.py --dry        # 只发请求，不调裁判
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.bombardment.scenarios_p0 import SCENARIOS
from tests.bombardment.judge import run_judges_parallel

MAX_WORKERS = 2
REQUEST_TIMEOUT = 120

# ── SSE 解析 ──

def _extract_sse_response(sse_body: str) -> str:
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
                        # 练习事件：questions 数组里才有实际内容
                        questions = nested.get("questions", [])
                        if isinstance(questions, list) and questions:
                            parts.append(json.dumps(questions, ensure_ascii=False))
                        # 可视化事件：blocks 数组
                        blocks = nested.get("blocks", [])
                        if isinstance(blocks, list) and blocks:
                            parts.append(json.dumps(blocks, ensure_ascii=False))
                        # 通用文本回答
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


# ── 单请求 ──

def _send_one(scenario: dict) -> dict:
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
        "endpoint": scenario.get("endpoint", ""),
        "category": scenario["category"],
        "description": scenario["description"],
        "status": status,
        "elapsed": round(elapsed, 2),
        "response": text,
        "response_len": len(text),
    }


# ── 并行轰炸 ──

def run_bombardment(scenarios: list[dict]) -> list[dict]:
    n = len(scenarios)
    results = [None] * n

    print(f"\n{'='*80}")
    print(f"  P0 核心用户链路轰炸测试 — {n} 个场景 — {datetime.now().strftime('%H:%M:%S')}")
    print(f"  并发数: {MAX_WORKERS}  |  目标: /api/chat + /tutor/chat")
    print(f"{'='*80}\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_send_one, s): i for i, s in enumerate(scenarios)}
        for f in as_completed(futures):
            result = f.result()
            for j, s in enumerate(scenarios):
                if s["id"] == result["id"]:
                    results[j] = result
                    break

            icon = "OK" if result["status"] == 200 else "FAIL"
            print(f"  [{icon}] {result['id']:<28s} "
                  f"{result['elapsed']:.1f}s  "
                  f"len={result['response_len']}  "
                  f"{result['description']}")

    return results


# ── 详细结果 ──

def _safe_print(text: str):
    """Windows GBK 安全打印，忽略终端无法编码的字符。"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("gbk", errors="replace").decode("gbk", errors="replace"))


def _truncate(text: str, max_len: int = 250) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def print_detailed_results(raw_results: list[dict]):
    """打印每个场景的详细请求/响应/裁判结果。"""
    print(f"\n{'='*80}")
    print("  逐场景详细结果")
    print(f"{'='*80}")

    for r in raw_results:
        endpoint = r.get("endpoint", "?")
        print(f"\n{'─'*80}")
        print(f"  [{r['id']}] {r['description']}")
        print(f"  端点: {endpoint}  |  耗时: {r['elapsed']}s  |  状态: {r['status']}  |  长度: {r['response_len']}")

        # 响应内容（截断）
        resp = r.get("response", "")
        if resp.startswith("[ERROR]") or resp.startswith("[TIMEOUT]") or resp.startswith("[HTTP"):
            print(f"  响应: {resp[:200]}")
        elif resp:
            print(f"  响应预览: {_truncate(resp, 300)}")

        # 裁判结果
        js = r.get("judge_score", {})
        if js:
            scores = js.get("scores", {})
            dims_str = "  ".join(f"{k}={v:.2f}" for k, v in scores.items())
            threshold = r.get("pass_threshold", 0.6)
            total = js.get("total", 0)
            passed = total >= threshold
            flag = "PASS" if passed else "FAIL"
            print(f"  裁判: total={total:.2f}  threshold={threshold}  [{flag}]")
            print(f"  维度: {dims_str}")
            print(f"  点评: {js.get('comment', '?')}")
        else:
            print(f"  裁判: 无评分数据")


# ── 汇总 ──

def print_summary(raw_results: list[dict]):
    print(f"\n{'='*80}")
    print("  P0 测试结果汇总")
    print(f"{'='*80}")

    # 端点分类统计
    for endpoint in ["/api/chat", "/tutor/chat"]:
        subset = [r for r in raw_results if r.get("endpoint") == endpoint]
        if not subset:
            continue
        ok = sum(1 for r in subset if r["status"] == 200)
        judged = [r for r in subset if "judge_score" in r]
        passes = sum(1 for r in judged if r["judge_score"].get("total", 0) >= r.get("pass_threshold", 0.6))
        times = [r["elapsed"] for r in subset if r["status"] == 200]
        avg_t = sum(times) / len(times) if times else 0
        totals = [r["judge_score"].get("total", 0) for r in judged]
        avg_s = sum(totals) / len(totals) if totals else 0

        print(f"\n  [{endpoint}] 成功率: {ok}/{len(subset)}  |  "
              f"平均耗时: {avg_t:.1f}s  |  "
              f"裁判通过: {passes}/{len(judged)}  |  "
              f"平均分: {avg_s:.2f}")

    # 总体
    valid = [r for r in raw_results if r["status"] == 200]
    judged = [r for r in raw_results if "judge_score" in r]

    if valid:
        times = [r["elapsed"] for r in valid]
        print(f"\n  总体响应时间: avg={sum(times)/len(times):.1f}s  "
              f"min={min(times):.1f}s  max={max(times):.1f}s")

    if judged:
        totals = [r["judge_score"].get("total", 0) for r in judged]
        passes = sum(1 for r in judged if r["judge_score"].get("total", 0) >= r.get("pass_threshold", 0.6))
        print(f"  总体裁判平均分: {sum(totals)/len(totals):.2f}  |  "
              f"通过率: {passes}/{len(judged)} ({passes/len(judged)*100:.0f}%)")

        print(f"\n  得分分布:")
        print(_ascii_histogram(totals, bins=5))

    # 失败/低分
    fails = [r for r in raw_results if r["status"] != 200]
    if fails:
        print(f"\n  [FAIL] {len(fails)} 个请求失败:")
        for r in fails:
            print(f"    - {r['id']}: status={r['status']}  {_truncate(r['response'], 100)}")

    low_scores = [r for r in judged if r["judge_score"].get("total", 0) < r.get("pass_threshold", 0.6)]
    if low_scores:
        print(f"\n  [LOW] {len(low_scores)} 个场景裁判未通过:")
        for r in low_scores:
            print(f"    - {r['id']}: {r['judge_score']['total']:.2f}  {r['judge_score'].get('comment', '')}")

    print(f"\n{'='*80}\n")


def _ascii_histogram(values: list[float], bins: int = 5) -> str:
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

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(LOG_DIR, exist_ok=True)


def _write_report(filename: str, text: str):
    path = os.path.join(LOG_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"[report] {path}")


def main():
    # Windows GBK 终端安全编码
    sys.stdout.reconfigure(encoding="utf-8", errors="replace") if hasattr(sys.stdout, "reconfigure") else None

    dry_run = "--dry" in sys.argv

    # 1. 并行轰炸
    raw_results = run_bombardment(SCENARIOS)

    if dry_run:
        print("\n--dry 模式，跳过 LLM 裁判。")
        print_detailed_results(raw_results)
        return

    # 2. LLM 裁判
    print(f"\n{'='*80}")
    print(f"  LLM 裁判评审 (DeepSeek v4 pro)")
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

        print(f"  [{jr.get('verdict', '?')}] {sid:<28s} "
              f"total={jr.get('total', 0):.2f}  "
              f"{jr.get('comment', '')[:80]}")

    # 4. 详细输出 + 汇总
    print_detailed_results(raw_results)
    print_summary(raw_results)


if __name__ == "__main__":
    main()
