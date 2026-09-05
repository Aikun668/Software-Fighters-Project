"""P5 Plan 测试：8 例学习计划 Goal→Decompose→Schedule

用法:
    cd ai-service && PYTHONPATH=. python tests/verify_p5_8_cases.py

设计:
  - P5 全链路: GoalAgent → DecomposeAgent → ScheduleAgent
  - Judge: qwen-max via DashScope, 流水线并发 4 + judge 串行 (避免资源竞争)
  - 加权 >85 PASS
"""
import asyncio, json, os, re, sys, time, traceback
from dataclasses import dataclass, field

from dotenv import load_dotenv
load_dotenv()

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import logging
logging.getLogger("app.utils.content_guard").setLevel(logging.ERROR)
logging.getLogger("app.utils.security_logger").setLevel(logging.ERROR)

from app.services.llm_service import OpenAILLM
from app.utils.prompt_loader import interpolate_variables, build_prompt

# ═══════════════════════ Judge ═══════════════════════

_judge_lock = asyncio.Lock()
_judge_llm = None; _judge_sys = ""; _judge_usr = ""; _judge_api_key = ""
PIPELINE_CONCURRENCY = 2  # 外部 API 单 key 并发 ≈3-5，压到 2 避免限速
JUDGE_MODEL = "qwen-max"
JUDGE_API_KEY = os.getenv("DASHSCOPE_API_KEY_MAX", "")
JUDGE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "")


async def _init_judge():
    global _judge_llm, _judge_sys, _judge_usr, _judge_api_key
    async with _judge_lock:
        if _judge_llm is not None:
            return
        # 只用 OpenAILLM 做 key resolution (_pick_key)，实际 HTTP 调走 aiohttp
        _judge_llm = OpenAILLM(temperature=0.0, max_tokens=512, use_mock=False,
                               model=JUDGE_MODEL, api_key=JUDGE_API_KEY, base_url=JUDGE_BASE_URL)
        _judge_api_key = _judge_llm.api_key
        _judge_sys = build_prompt("tutor_agent", filename="plan_judge.yaml", key="system")
        _judge_usr = build_prompt("tutor_agent", filename="plan_judge.yaml", key="user")


async def _call_judge(question: str, difficulty: int, response: str) -> dict | None:
    """Judge call using aiohttp (httpx has connection issues on this Windows env)."""
    import aiohttp
    user_prompt = interpolate_variables(_judge_usr, {
        "question": question[:300], "difficulty": str(difficulty), "response": response[:4000],
    })
    url = f"{JUDGE_BASE_URL}/chat/completions"
    messages = [{"role": "system", "content": _judge_sys},
                {"role": "user", "content": user_prompt}]
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
                async with session.post(
                    url,
                    json={"model": JUDGE_MODEL, "messages": messages, "temperature": 0.0, "max_tokens": 512, "stream": False},
                    headers={"Authorization": f"Bearer {_judge_api_key}", "Content-Type": "application/json"},
                ) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        raise RuntimeError(f"HTTP {resp.status}: {err_text[:200]}")
                    data = await resp.json()
                    text = data["choices"][0]["message"]["content"]
            text = text.strip()
            if not text:
                print(f"  [judge WARN] empty response, attempt {attempt+1}/3", file=sys.stderr)
                if attempt < 2:
                    await asyncio.sleep(2.0)
                continue
            if text.startswith("```"): text = re.sub(r"^```(?:json)?\s*", "", text); text = re.sub(r"\s*```$", "", text)
            j = json.loads(text)
            if isinstance(j, dict) and "total" in j:
                return j
            print(f"  [judge WARN] missing 'total' key, got keys={list(j.keys())}, attempt {attempt+1}/3", file=sys.stderr)
            if attempt < 2:
                await asyncio.sleep(1.5)
        except json.JSONDecodeError as e:
            print(f"  [judge WARN] JSON parse error: {e}, text={text[:200]!r}, attempt {attempt+1}/3", file=sys.stderr)
            if attempt < 2:
                await asyncio.sleep(1.5)
        except Exception as e:
            print(f"  [judge WARN] {type(e).__name__}: {e}, attempt {attempt+1}/3", file=sys.stderr)
            if attempt < 2:
                await asyncio.sleep(1.5)
    print(f"  [judge FAIL] all 3 attempts exhausted", file=sys.stderr)
    return None


def _jd(j: dict, elapsed_ms: float) -> dict:
    return {"A": j.get("accuracy",0), "D": j.get("depth",0), "H": j.get("helpfulness",0),
            "S": j.get("structure",0), "F": j.get("domain_fit",0),
            "total": j.get("total",0), "brief": j.get("brief",""), "ms": round(elapsed_ms,1)}


# ═══════════════════════ 用例 (8例，由难到易) ═══════════════════════

CASES = [
    {"id": 1, "diff": 3, "input": "三个月准备大厂ML面试，已有两年Python经验，数学基础不错（考研数学135），"
     "每天能投入4小时。希望覆盖：机器学习基础算法、深度学习、以及一些ML系统设计的知识。",
     "desc": "面试备战：强基础+明确时间+多领域"},
    {"id": 2, "diff": 3, "input": "想用AI做量化交易策略。目前情况：Python熟练但金融和ML都是半吊子——"
     "上过一门金融入门课、用sklearn做过简单分类。不知道从哪里系统学。",
     "desc": "交叉学科模糊目标：量化+ML双线"},
    {"id": 3, "diff": 2, "input": "下个月想入门NLP，之前做过图像分类（用ResNet微调过）。数学还行，每周能投入15小时左右。",
     "desc": "转方向：CV→NLP+时间明确"},
    {"id": 4, "diff": 2, "input": "毕业论文要写图神经网络方面的，但我GNN零基础。三个月时间，每天大概3小时，希望能从入门到能复现论文。",
     "desc": "学术目标：GNN零基础+论文导向"},
    {"id": 5, "diff": 2, "input": "两周内学会用sklearn做分类和回归，要能独立完成一个简单的预测项目。"
     "有Python基础但没做过ML，每天1.5小时。",
     "desc": "短期实操：具体工具+时间紧"},
    {"id": 6, "diff": 1, "input": "刚学完Python基础（列表、字典、函数、类），下一步该学什么来入门AI？每天大概2小时。",
     "desc": "入门转折：有编程不知方向"},
    {"id": 7, "diff": 1, "input": "每天只有1小时学AI，帮我安排一周的学习计划。目前零基础，想看看AI是什么。",
     "desc": "极简微计划：零基础+极短时间"},
    {"id": 8, "diff": 1, "input": "帮我制定一个机器学习入门学习计划。",
     "desc": "一句话：无任何背景信息"},
]


# ═══════════════════════ 格式化 ═══════════════════════

def _fmt_plan(goal: dict, decomp: dict, sched: dict) -> str:
    lines = []
    if goal:
        lines.append("【目标提取】")
        lines.append(f"  标题: {goal.get('goal_title', '')}")
        lines.append(f"  主题: {goal.get('target_topic', '')}")
        lines.append(f"  层级: {goal.get('target_level', '')}")
        lines.append(f"  截止: {goal.get('deadline', '') or '未指定'}")
        lines.append(f"  动机: {goal.get('motivation', '')}")
        lines.append(f"  约束: {', '.join(goal.get('constraints', [])) or '无'}")
    if decomp:
        lines.append("")
        lines.append("【知识点拆解】")
        macros = decomp.get("macro_topics", [])
        micros = decomp.get("micro_skills", [])
        prereqs = decomp.get("prerequisites", [])
        for m in macros:
            lines.append(f"  宏观: {m.get('name','')} (bloom={m.get('bloom_level','')}) — {m.get('description','')[:100]}")
        for m in micros:
            lines.append(f"  微观: {m.get('name','')} (bloom={m.get('bloom_level','')}, parent={m.get('parent','')}) — {m.get('description','')[:100]}")
        for p in prereqs:
            lines.append(f"  前置: {p.get('name','')} ({p.get('relation','')}) — {p.get('description','')[:100]}")
        if decomp.get("summary"):
            lines.append(f"  概述: {decomp['summary']}")
    if sched:
        lines.append("")
        lines.append("【每日排期】")
        lines.append(f"  标题: {sched.get('plan_title', '')}")
        lines.append(f"  总天数: {sched.get('estimated_days', '?')} | 每日容量: {sched.get('daily_capacity', '?')} 任务")
        for s in sched.get("steps", []):
            lines.append(f"  Day{s.get('day','?')}: [{s.get('type','?')}|{s.get('bloom_level','?')}] {s.get('topic','')} — {s.get('description','')[:120]}")
        lines.append(f"  里程碑: {' | '.join(sched.get('milestones', []))}")
    return "\n".join(lines)


# ═══════════════════════ Runner ═══════════════════════

@dataclass
class CaseResult:
    case_id: int; diff: int; desc: str
    score: float = 0.0; details: dict = field(default_factory=dict)
    errors: list = field(default_factory=list); raw: str = ""
    raw_data: dict = field(default_factory=dict)


async def _run_pipeline(case: dict) -> tuple[str, list[str], dict]:
    """Run plan pipeline for one case, return (plan_text, errors, raw_data)."""
    errors = []; plan_text = ""; raw_data = {}
    try:
        from app.agents.goal_agent import GoalAgent
        from app.agents.decompose_agent import DecomposeAgent
        from app.agents.schedule_agent import ScheduleAgent

        has_api = bool(os.getenv("MINIMAX_API_KEY") or os.getenv("OPENAI_API_KEY")
                       or os.getenv("DASHSCOPE_API_KEY") or os.getenv("DASHSCOPE_API_KEY_FLASH"))

        ga = GoalAgent(use_mock_llm=not has_api)
        gs_raw = await ga.run({"input": case["input"], "context": "", "student_profile": {}})
        goal = {"goal_title": gs_raw.get("goal_title",""), "target_topic": gs_raw.get("target_topic",""),
                "target_level": gs_raw.get("target_level",""), "deadline": gs_raw.get("deadline",""),
                "motivation": gs_raw.get("motivation",""), "constraints": gs_raw.get("constraints",[])}

        da = DecomposeAgent(use_mock_llm=not has_api)
        ds_raw = await da.run({"topic": goal.get("target_topic", case["input"]), "context": case["input"], "student_profile": {}})
        decomp = {"macro_topics": ds_raw.get("macro_topics",[]), "micro_skills": ds_raw.get("micro_skills",[]),
                  "prerequisites": ds_raw.get("prerequisites",[]), "summary": ds_raw.get("summary","")}

        sa = ScheduleAgent(use_mock_llm=not has_api)
        ss_raw = await sa.run({"goal": goal, "decomposition": decomp, "student_profile": {}, "existing_plan": {}})
        sched = {"plan_title": ss_raw.get("plan_title",""), "estimated_days": ss_raw.get("estimated_days",0),
                 "daily_capacity": ss_raw.get("daily_capacity",0), "steps": ss_raw.get("steps",[]),
                 "milestones": ss_raw.get("milestones",[])}

        plan_text = _fmt_plan(goal, decomp, sched)
        raw_data = {"goal": gs_raw, "decomp": ds_raw, "sched": ss_raw}
    except Exception as e:
        errors.append(f"{type(e).__name__}: {e}")
        traceback.print_exc()
    return plan_text, errors, raw_data


async def run_all() -> list[CaseResult]:
    pipeline_sem = asyncio.Semaphore(PIPELINE_CONCURRENCY)

    # ── Phase 1: 并发跑流水线 ──
    async def phase1(i, case):
        # 错峰启动：每 2 秒放一个，避免同时冲击 API
        await asyncio.sleep(i * 2.0)
        async with pipeline_sem:
            t0 = time.perf_counter()
            plan_text, errors, raw_data = await _run_pipeline(case)
            elapsed = (time.perf_counter() - t0) * 1000
            return {
                "case": case,
                "plan_text": plan_text,
                "errors": errors,
                "raw_data": raw_data,
                "pipeline_ms": elapsed,
            }

    print(f"\n  [Phase 1] 并发={PIPELINE_CONCURRENCY} 跑 {len(CASES)} 条流水线...\n")
    pipeline_results = list(await asyncio.gather(*[phase1(i, c) for i, c in enumerate(CASES)]))

    # ── Phase 2: 串行 judge (避免 HTTP 连接池竞争) ──
    # ── 存盘路径 ──
    output_path = os.path.join(os.path.dirname(__file__), "_p5_full_output.json")

    print(f"\n  [Phase 2] 串行 judge 评分...\n")
    results = []
    for pr in pipeline_results:
        case = pr["case"]
        t0 = time.perf_counter()
        judge = None
        if pr["plan_text"] and not pr["errors"]:
            judge = await _call_judge(case["input"][:300], case["diff"], pr["plan_text"])

        score = float(judge["total"]) if judge else 0.0
        elapsed = (time.perf_counter() - t0) * 1000
        details = {"judge_ok": judge is not None, "pipeline_ms": pr["pipeline_ms"]}
        if judge:
            details.update(_jd(judge, elapsed))
        results.append(CaseResult(
            case_id=case["id"], diff=case["diff"], desc=case["desc"],
            score=score, details=details, errors=pr["errors"],
            raw=pr["plan_text"][:500],
            raw_data=pr.get("raw_data", {}),
        ))
        if judge:
            print(f"  [case {case['id']}] scored {score:.0f}/100 ({elapsed:.0f}ms)")
        else:
            print(f"  [case {case['id']}] judge FAILED")

    # ── 保存完整 raw data ──
    saved = []
    for pr, r in zip(pipeline_results, results):
        saved.append({
            "id": r.case_id,
            "diff": r.diff,
            "desc": r.desc,
            "input": pr["case"]["input"],
            "score": r.score,
            "judge_details": r.details,
            "errors": r.errors,
            "raw_data": pr.get("raw_data", {}),
        })
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(saved, f, ensure_ascii=False, indent=2)
    print(f"\n  完整输出已保存: {output_path}")

    return results


# ═══════════════════════ Report ═══════════════════════

DIFF = {1: "★☆☆", 2: "★★☆", 3: "★★★"}

def report(results: list[CaseResult]) -> bool:
    print("\n" + "=" * 80)
    print(f"  P5 Plan 测试报告 (8例)  |  Judge: {JUDGE_MODEL}  |  流水线并发:4 + Judge串行")
    print("=" * 80)

    for r in results:
        d = DIFF.get(r.diff, "???")
        status = "[PASS]" if r.score >= 70 else "[FAIL]"
        print(f"\n  [{r.case_id}] {d} {status} ({r.score:.0f}/100) | {r.desc}")
        if r.errors:
            for e in r.errors: print(f"       ERROR: {e}")
        j = r.details
        if j.get("judge_ok"):
            print(f"       A{j['A']} D{j['D']} H{j['H']} S{j['S']} F{j['F']} | pipeline={j.get('pipeline_ms','?'):.0f}ms judge={j['ms']:.0f}ms")
            print(f"       brief: {j['brief']}")
        else:
            print(f"       (judge 不可用)  pipeline={j.get('pipeline_ms','?'):.0f}ms")
        if r.raw:
            preview = r.raw[:200].replace('\n', ' ')
            print(f"       plan: {preview}...")

    avg = sum(r.score for r in results) / len(results)
    passed = sum(1 for r in results if r.score >= 70)
    verdict = "[PASS]" if avg >= 85 else "[FAIL]"
    print(f"\n{'─' * 60}")
    print(f"  avg={avg:.1f} {verdict}  pass={passed}/{len(results)}")
    for diff in [1,2,3]:
        dr = [r for r in results if r.diff == diff]
        if dr:
            a = sum(r.score for r in dr) / len(dr)
            print(f"  {DIFF[diff]} ({len(dr)}例) avg={a:.1f}  pass={sum(1 for r in dr if r.score>=70)}/{len(dr)}")
    print("=" * 80)
    return avg >= 85


async def main():
    print("=" * 80)
    print("  P5 Plan：GoalAgent → DecomposeAgent → ScheduleAgent")
    print("=" * 80)
    await _init_judge()
    print(f"  Judge: {JUDGE_MODEL} (key: ...{_judge_api_key[-4:] if _judge_api_key else 'N/A'})")
    results = await run_all()
    return 0 if report(results) else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
