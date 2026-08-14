"""
可视化专项测试 — 主入口

用法:
  python tests/bombardment/run_visual.py              # 完整测试（轰炸 + 裁判）
  python tests/bombardment/run_visual.py --dry        # 只发请求，不调裁判
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.bombardment.scenarios_visual import SCENARIOS
from tests.bombardment.judge import call_judge

MAX_WORKERS = 1
REQUEST_TIMEOUT = 180
REQUEST_DELAY = 5  # 请求间隔（秒），避免服务过载

# ── 确定性校验（程序化，零 LLM 成本）──

try:
    from app.agents.visualize.utils import validate_visualization as _validate_viz
except ImportError:
    _validate_viz = None


def _deterministic_check(blocks: list[dict]) -> dict:
    """对提取到的 blocks 逐一做确定性校验，返回汇总结果。"""
    if not blocks:
        return {"has_blocks": False, "checks": [], "all_valid": None}

    checks = []
    for b in blocks:
        code = b.get("code", "")
        render_type = b.get("type", "unknown")
        if _validate_viz and code:
            ok, err = _validate_viz(code, render_type)
        else:
            ok, err = (True, "")  # 无法校验时不过滤

        checks.append({
            "type": render_type,
            "title": b.get("title", ""),
            "code_len": len(code),
            "valid": ok,
            "error": err,
        })

    all_ok = all(c["valid"] for c in checks)
    return {"has_blocks": True, "checks": checks, "all_valid": all_ok}


# ── 代码清洗 ──

def _strip_markdown_fence(code: str) -> str:
    """去掉 markdown 代码块标记 (```mermaid ... ```)。"""
    text = code.strip()
    if text.startswith("```"):
        # 找到第一行换行符
        nl = text.find("\n")
        if nl > 0:
            text = text[nl + 1:]
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


# ── SSE 解析（提取文本 + 结构化 blocks）──

def _extract_sse_full(sse_body: str) -> dict:
    """从 SSE 流中提取文本回答和结构化 blocks。"""
    text_parts = []
    blocks = []

    for line in sse_body.split("\n"):
        if not line.startswith("data: "):
            continue
        data = line[6:]
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue

        t = event.get("type", "")

        if t == "content":
            nested = event.get("data", {})
            if isinstance(nested, dict):
                # 文本回答
                r = nested.get("response", "")
                if isinstance(r, str) and r:
                    text_parts.append(r)

                # 练习题
                questions = nested.get("questions", [])
                if isinstance(questions, list) and questions:
                    text_parts.append(json.dumps(questions, ensure_ascii=False))

                # 可视化 blocks
                raw_blocks = nested.get("blocks", [])
                if isinstance(raw_blocks, list):
                    for b in raw_blocks:
                        if isinstance(b, dict) and b.get("code"):
                            code = _strip_markdown_fence(b.get("code", ""))
                            blocks.append({
                                "type": b.get("type", "unknown"),
                                "title": b.get("title", ""),
                                "code": code,
                                "source": "pipeline",  # 结构化 blocks 来自可视化管线
                            })

        elif t == "token":
            c = event.get("content", "")
            if isinstance(c, str):
                text_parts.append(c)

        elif t == "error":
            return {"text": f"[ERROR] {event.get('content', 'unknown')}", "blocks": []}

    full_text = "".join(text_parts).strip()

    # 若没有结构化 blocks，尝试从文本中提取 mermaid/svg/chartjs 代码块
    if not blocks and full_text:
        fallback_blocks = _extract_blocks_from_markdown(full_text)
        blocks.extend(fallback_blocks)

    return {"text": full_text, "blocks": blocks}


def _extract_blocks_from_markdown(text: str) -> list[dict]:
    """从 markdown 文本中提取 ```mermaid / ```svg / ```chartjs 代码块作为 fallback。

    注意：```lang 之后的文字（如 ```mermaid graph TD）属于代码第一行，不能丢弃。
    """
    import re as _re
    blocks = []
    # 匹配: ```lang [optional-first-line]\n...content...```
    # group(1)=lang, group(2)=optional first line after lang, group(3)=rest of code
    pattern = _re.compile(
        r"```(mermaid|svg|chartjs|html)(?:[ \t]+([^\n]*))?\n(.*?)```",
        _re.DOTALL,
    )
    for m in pattern.finditer(text):
        lang = m.group(1)
        first_line = m.group(2)  # 可能是 None（lang 后直接换行）
        body = m.group(3)
        # 拼接: 如果 lang 后有内容（如 "graph TD"），它属于代码第一行
        if first_line:
            code = first_line + "\n" + body
        else:
            code = body
        code = code.strip()
        if code:
            blocks.append({
                "type": lang,
                "title": f"inline_{lang}_block",
                "code": code,
                "source": "markdown_inline",  # 标记为 tutor 内联生成
            })
    return blocks


# ── 单请求发送 ──

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
            parsed = _extract_sse_full(r.text)
            text = parsed["text"]
            blocks = parsed["blocks"]
            # 无文本但有 blocks 时不回退到 raw SSE
            if not text and not blocks:
                try:
                    data = r.json()
                    text = json.dumps(data, ensure_ascii=False, indent=2)
                except Exception:
                    text = r.text[:3000]
            elif not text and blocks:
                text = f"[可视化生成] {len(blocks)} 个代码块"
        else:
            text = f"[HTTP {status}] {r.text[:500]}"
            blocks = []

    except (requests.exceptions.Timeout, requests.Timeout):
        elapsed = time.time() - t0
        status = -1
        text = "[TIMEOUT] 请求超时"
        blocks = []
    except Exception as e:
        elapsed = time.time() - t0
        status = -2
        text = f"[EXCEPTION] {e}"
        blocks = []

    # 确定性校验
    det_result = _deterministic_check(blocks)

    return {
        "id": scenario["id"],
        "endpoint": scenario.get("endpoint", ""),
        "category": scenario["category"],
        "description": scenario["description"],
        "expected_trigger": scenario.get("expected_trigger"),
        "expected_types": scenario.get("expected_types", []),
        "status": status,
        "elapsed": round(elapsed, 2),
        "response": text,
        "response_len": len(text),
        "blocks": blocks,
        "det_check": det_result,
    }


# ── 并行轰炸 ──

def run_bombardment(scenarios: list[dict]) -> list[dict]:
    n = len(scenarios)
    results = []

    print(f"\n{'='*80}")
    print(f"  可视化专项测试 — {n} 个场景 — {datetime.now().strftime('%H:%M:%S')}")
    print(f"  串行模式 (间隔 {REQUEST_DELAY}s)  |  目标: /api/chat (mode=auto)")
    print(f"{'='*80}\n")

    for i, s in enumerate(scenarios):
        result = _send_one(s)

        det = result["det_check"]
        if det["has_blocks"]:
            if det["all_valid"]:
                det_icon = "DET_OK"
            elif det["all_valid"] is False:
                det_icon = "DET_FAIL"
            else:
                det_icon = "DET_??"
        else:
            det_icon = "NO_BLK"

        # 区分 pipeline 和 markdown_inline 来源
        sources = set(b.get("source", "?") for b in result.get("blocks", []))
        if "pipeline" in sources:
            triggered = "PIPELINE"
        elif "markdown_inline" in sources:
            triggered = "INLINE"
        else:
            triggered = "TXT"

        exp = result["expected_trigger"]
        exp_str = "EXP_VIS" if exp else ("EXP_TXT" if exp is False else "EXP_ANY")
        match_str = ""
        has_any_viz = bool(result["blocks"])
        if exp is True and not has_any_viz:
            match_str = " [MISS: 应触发未触发!]"
        elif exp is False and "pipeline" in sources:
            match_str = " [FALSE: pipeline误触发!]"

        icon = "OK" if result["status"] == 200 else "FAIL"
        print(f"  [{icon}] {result['id']:<30s} {result['elapsed']:.1f}s  "
              f"[{triggered}] [{det_icon}] {exp_str}  "
              f"blocks={len(result['blocks'])} len={result['response_len']}{match_str}")

        results.append(result)

        # 间隔让服务喘息
        if i < n - 1 and result["status"] == 200:
            time.sleep(REQUEST_DELAY)

    return results


# ── 裁判阶段 ──

def run_judges(raw_results: list[dict]) -> list[dict]:
    """对成功响应调用 LLM 裁判，融合确定性校验结果。"""
    judge_inputs = []
    for r in raw_results:
        if r["status"] != 200 or not r["response"]:
            continue
        # 找到对应的 scenario
        scenario = next((s for s in SCENARIOS if s["id"] == r["id"]), None)
        if scenario is None:
            continue
        judge_inputs.append((scenario, r))

    if not judge_inputs:
        print("没有可评审的成功响应，跳过裁判。")
        return raw_results

    print(f"\n{'='*80}")
    print(f"  LLM 裁判评审 (DeepSeek v4 pro)")
    print(f"{'='*80}\n")

    for scenario, result in judge_inputs:
        rubric_template = scenario["judge"]["rubric"]

        # 构建包含确定性校验信息 + 文本回答的评审内容
        det = result["det_check"]
        det_note_parts = []
        if det["has_blocks"]:
            for i, c in enumerate(det["checks"]):
                status_str = "PASS" if c["valid"] else f"FAIL: {c['error']}"
                det_note_parts.append(
                    f"Block{i+1}: type={c['type']}, title={c['title']}, "
                    f"code_len={c['code_len']}, deterministic_validation={status_str}"
                )
        else:
            det_note_parts.append("未生成可视化代码块。")

        # 将确定性校验结果注入 rubric
        injected_rubric = rubric_template.replace(
            "{extra_context}",
            scenario["judge"].get("rubric", "").split("{extra_context}")[1].split("\n\n输出严格")[0]
            if "{extra_context}" in rubric_template
            else ""
        )

        # 构建完整的待评审内容
        response_for_judge = (
            f"[确定性校验结果]\n"
            + "\n".join(det_note_parts)
            + f"\n\n[AI回答文本]\n{result['response'][:2500]}"
        )

        jr = call_judge(scenario["judge"]["rubric"], response_for_judge)
        jr["scenario_id"] = scenario["id"]

        # 融合确定性校验 → code_validity 维度
        if det["has_blocks"] and det["all_valid"] is not None:
            det_score = 1.0 if det["all_valid"] else 0.0
            # LLM 的 code_validity 和确定性校验取平均
            llm_cv = jr.get("scores", {}).get("code_validity", det_score)
            jr.setdefault("scores", {})["code_validity"] = round((llm_cv + det_score) / 2, 2)
            jr["scores"]["_det_code_validity"] = det_score
            jr["scores"]["_llm_code_validity"] = llm_cv
            # 重算 total
            raw_scores = {k: v for k, v in jr["scores"].items() if not k.startswith("_")}
            if raw_scores:
                jr["total"] = round(sum(raw_scores.values()) / len(raw_scores), 2)

        result["judge_score"] = {
            "scores": jr.get("scores", {}),
            "total": jr.get("total", 0),
            "verdict": jr.get("verdict", "ERROR"),
            "comment": jr.get("comment", ""),
        }
        result["pass_threshold"] = scenario["judge"]["pass_threshold"]

        icon = "PASS" if result["judge_score"]["total"] >= result["pass_threshold"] else "FAIL"
        print(f"  [{icon}] {scenario['id']:<30s} "
              f"total={result['judge_score']['total']:.2f}  "
              f"{result['judge_score'].get('comment', '')[:80]}")

    return raw_results


# ── 打印 ──

def _safe_print(text: str):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("gbk", errors="replace").decode("gbk", errors="replace"))


def _truncate(text: str, max_len: int = 250) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def print_detailed_results(raw_results: list[dict]):
    print(f"\n{'='*80}")
    print("  逐场景详细结果")
    print(f"{'='*80}")

    for r in raw_results:
        print(f"\n{'─'*80}")
        exp = r.get("expected_trigger")
        exp_str = "应触发" if exp else ("不应触发" if exp is False else "无要求")
        print(f"  [{r['id']}] {r['description']}  |  {exp_str}")
        print(f"  端点: {r.get('endpoint', '?')}  |  耗时: {r['elapsed']}s  |  "
              f"状态: {r['status']}  |  文本长度: {r['response_len']}")

        # 可视化触发情况
        blocks = r.get("blocks", [])
        if blocks:
            print(f"  可视化: 触发  |  blocks数量: {len(blocks)}")
            for i, b in enumerate(blocks):
                print(f"    Block{i+1}: type={b['type']}, title={b.get('title','')}, "
                      f"code_len={len(b.get('code',''))}")
        else:
            print(f"  可视化: 未触发")

        # 确定性校验
        det = r.get("det_check", {})
        if det.get("has_blocks"):
            for c in det["checks"]:
                status_str = "PASS" if c["valid"] else f"FAIL: {c['error']}"
                print(f"  确定性校验 [{c['type']}]: {status_str}")

        # 响应预览
        resp = r.get("response", "")
        if resp.startswith("[ERROR]") or resp.startswith("[TIMEOUT]") or resp.startswith("[HTTP"):
            print(f"  响应: {resp[:200]}")
        elif resp:
            print(f"  响应预览: {_truncate(resp, 300)}")

        # 裁判结果
        js = r.get("judge_score", {})
        if js:
            scores = js.get("scores", {})
            dims_str = "  ".join(
                f"{k}={v:.2f}" for k, v in scores.items() if not k.startswith("_")
            )
            threshold = r.get("pass_threshold", 0.6)
            total = js.get("total", 0)
            passed = total >= threshold
            flag = "PASS" if passed else "FAIL"
            print(f"  裁判: total={total:.2f}  threshold={threshold}  [{flag}]")
            print(f"  维度: {dims_str}")
            # 显示确定性校验细节
            det_scores = {k: v for k, v in scores.items() if k.startswith("_")}
            if det_scores:
                print(f"  内部: {json.dumps(det_scores, ensure_ascii=False)}")
            print(f"  点评: {js.get('comment', '?')}")
        else:
            print(f"  裁判: 无评分数据")


def print_summary(raw_results: list[dict]):
    print(f"\n{'='*80}")
    print("  可视化专项测试汇总")
    print(f"{'='*80}")

    # 按类别分
    categories = {}
    for r in raw_results:
        cat = r.get("category", "其他")
        categories.setdefault(cat, []).append(r)

    for cat, items in categories.items():
        ok = sum(1 for r in items if r["status"] == 200)
        judged = [r for r in items if "judge_score" in r]
        passes = sum(1 for r in judged
                     if r["judge_score"].get("total", 0) >= r.get("pass_threshold", 0.6))
        times = [r["elapsed"] for r in items if r["status"] == 200]
        avg_t = sum(times) / len(times) if times else 0

        print(f"\n  [{cat}] 成功率: {ok}/{len(items)}  |  "
              f"平均耗时: {avg_t:.1f}s  |  "
              f"裁判通过: {passes}/{len(judged)}")

    # 可视化触发正确性
    print(f"\n  可视化触发正确性:")
    correct_trigger = 0
    total_trigger = 0
    for r in raw_results:
        exp = r.get("expected_trigger")
        if exp is None:
            continue
        total_trigger += 1
        actual_triggered = bool(r.get("blocks"))
        if exp == actual_triggered:
            correct_trigger += 1
        else:
            direction = "MISS(应触发未触发)" if exp else "FALSE(不应触发却触发)"
            print(f"    [{direction}] {r['id']}: {r['description']}")

    if total_trigger:
        print(f"  触发正确率: {correct_trigger}/{total_trigger} "
              f"({correct_trigger/total_trigger*100:.0f}%)")

    # 总体统计
    valid = [r for r in raw_results if r["status"] == 200]
    judged = [r for r in raw_results if "judge_score" in r]

    if valid:
        times = [r["elapsed"] for r in valid]
        print(f"\n  总体响应时间: avg={sum(times)/len(times):.1f}s  "
              f"min={min(times):.1f}s  max={max(times):.1f}s")

    if judged:
        totals = [r["judge_score"].get("total", 0) for r in judged]
        passes = sum(1 for r in judged
                     if r["judge_score"].get("total", 0) >= r.get("pass_threshold", 0.6))
        print(f"  总体裁判平均分: {sum(totals)/len(totals):.2f}  |  "
              f"通过率: {passes}/{len(judged)} ({passes/len(judged)*100:.0f}%)")

        print(f"\n  得分分布:")
        print(_ascii_histogram(totals, bins=5))

    # 确定性校验统计
    det_checks = []
    for r in raw_results:
        det = r.get("det_check", {})
        for c in det.get("checks", []):
            det_checks.append(c)
    if det_checks:
        det_ok = sum(1 for c in det_checks if c["valid"])
        print(f"\n  确定性校验: {det_ok}/{len(det_checks)} 通过")

    # 失败汇总
    fails = [r for r in raw_results if r["status"] != 200]
    if fails:
        print(f"\n  [FAIL] {len(fails)} 个请求失败:")
        for r in fails:
            print(f"    - {r['id']}: status={r['status']}  {_truncate(r['response'], 100)}")

    low_scores = [r for r in judged
                  if r["judge_score"].get("total", 0) < r.get("pass_threshold", 0.6)]
    if low_scores:
        print(f"\n  [LOW] {len(low_scores)} 个场景裁判未通过:")
        for r in low_scores:
            print(f"    - {r['id']}: {r['judge_score']['total']:.2f}  "
                  f"{r['judge_score'].get('comment', '')}")

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
        bar = "|" * int(buckets[i] / max_count * bar_max)
        lines.append(f"  {low:.1f}-{high:.1f}  {bar}  {buckets[i]}")
    return "\n".join(lines)


# ═══════════════════════ 主流程 ═══════════════════════

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(LOG_DIR, exist_ok=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace") if hasattr(sys.stdout, "reconfigure") else None

    dry_run = "--dry" in sys.argv

    # 1. 并行轰炸
    raw_results = run_bombardment(SCENARIOS)

    if dry_run:
        print("\n--dry 模式，跳过 LLM 裁判。")
        print_detailed_results(raw_results)
        print_summary(raw_results)
        return

    # 2. LLM 裁判
    raw_results = run_judges(raw_results)

    # 3. 详细输出 + 汇总
    print_detailed_results(raw_results)
    print_summary(raw_results)


if __name__ == "__main__":
    main()
