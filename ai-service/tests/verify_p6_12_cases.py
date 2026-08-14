"""P6 Solve 测试：12 例 SolveAgent Plan→Solve→Review

用法:
    cd ai-service && PYTHONPATH=. python tests/verify_p6_12_cases.py

设计:
  - P6 全链路: SolveAgent (Plan → Solve → Review)
  - Judge: qwen-max, 流水线并发 2 + judge 串行
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

from app.utils.prompt_loader import interpolate_variables, build_prompt

# ═══════════════════════ Judge ═══════════════════════

_judge_lock = asyncio.Lock()
_judge_sys = ""; _judge_usr = ""; _judge_api_key = ""
PIPELINE_CONCURRENCY = 2
JUDGE_MODEL = "qwen-max"
JUDGE_API_KEY = os.getenv("DASHSCOPE_API_KEY_MAX", "")
JUDGE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "")


async def _init_judge():
    global _judge_sys, _judge_usr, _judge_api_key
    async with _judge_lock:
        if _judge_sys:
            return
        _judge_api_key = JUDGE_API_KEY
        _judge_sys = build_prompt("tutor_agent", filename="solve_judge.yaml", key="system")
        _judge_usr = build_prompt("tutor_agent", filename="solve_judge.yaml", key="user")


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


# ═══════════════════════ 用例 (12例，由难到易) ═══════════════════════

CASES = [
    {"id": 1, "diff": 3,
     "question": "请推导SVM的对偶问题，从原始优化问题出发，"
                 "写出拉格朗日函数、对偶函数、以及对偶问题的最终形式，并解释为什么对偶形式适合引入核函数。",
     "desc": "SVM对偶推导：多步公式+核技巧原理"},
    {"id": 2, "diff": 3,
     "question": "我训练了一个ResNet-18做10分类，训练集accuracy 98%但验证集一直在50%左右徘徊。"
                 "学习率0.1，batch_size=128，用了SGD+momentum。请分析可能的原因并给出诊断步骤。",
     "desc": "训练调试：严重过拟合+架构选择+超参分析"},
    {"id": 3, "diff": 3,
     "question": "给定数据点：[(1, 1.8), (2, 4.2), (3, 5.8), (4, 8.1), (5, 9.9)]。"
                 "请用最小二乘法求线性拟合 y=ax+b，写出正规方程过程并计算R²。",
     "desc": "数值计算：最小二乘法+矩阵运算+R²"},
    {"id": 4, "diff": 3,
     "question": "请详细推导神经网络中反向传播算法：对于一个三层全连接网络（输入d维、"
                 "隐层h维、输出k维，均用sigmoid激活，损失用MSE），推导损失对第二层权重W^(2)的梯度公式。",
     "desc": "反向传播推导：链式法则+矩阵微积分"},
    {"id": 5, "diff": 2,
     "question": "Batch Normalization和Layer Normalization有什么区别？"
                 "分别在什么场景下更适用？为什么Transformer用LayerNorm而CNN用BatchNorm？",
     "desc": "概念辨析：BN vs LN+使用场景+架构适配"},
    {"id": 6, "diff": 2,
     "question": "请解释Transformer中Multi-Head Attention的完整计算过程，"
                 "包括Q、K、V的来源、缩放因子的作用、以及多头拼接后的处理。",
     "desc": "注意力机制：QKV+缩放+多头+线性投影"},
    {"id": 7, "diff": 2,
     "question": "为什么分类任务用交叉熵损失而不用MSE？请从梯度角度详细解释，"
                 "并推导sigmoid输出层下两种损失的梯度公式对比。",
     "desc": "损失函数对比：梯度消失+收敛速度+推导"},
    {"id": 8, "diff": 2,
     "question": "L1正则化和L2正则化有什么区别？为什么L1正则化倾向于产生稀疏解而L2不会？"
                 "请从几何直观和数学推导两个角度解释。",
     "desc": "正则化对比：稀疏性+几何直观+优化角度"},
    {"id": 9, "diff": 1,
     "question": "什么是过拟合？有哪些常见的判断方法和预防手段？",
     "desc": "基础概念：过拟合定义+判断+预防"},
    {"id": 10, "diff": 1,
     "question": "已知参数向量 w=[2.0, 1.5]，学习率 α=0.01，当前梯度 ∇L=[0.5, -0.3]。"
                 "请计算一步梯度下降后的参数值，并解释梯度方向与更新方向的关系。",
     "desc": "基础计算：梯度下降一步更新+方向解释"},
    {"id": 11, "diff": 1,
     "question": "什么是反向传播？请用通俗易懂的语言解释它的基本思想，"
                 "不需要公式，让零基础的人也能理解。",
     "desc": "零基础解释：反向传播直觉+无公式要求"},
    {"id": 12, "diff": 1,
     "question": "梯度下降（GD）和随机梯度下降（SGD）有什么区别？各有什么优缺点？",
     "desc": "基础对比：GD vs SGD定义+优缺点"},
]


# ═══════════════════════ 格式化 ═══════════════════════

def _fmt_solve(state: dict) -> str:
    lines = []
    steps = state.get("steps", [])
    if steps:
        lines.append(f"【解题步骤 ({len(steps)}步)】")
        for s in steps:
            lines.append(f"  第{s.get('step','?')}步 {s.get('title','')}: {s.get('goal','')}")
    solution = state.get("solution", "")
    if solution:
        lines.append(f"\n【解答内容】")
        lines.append(solution[:2000])
    conf = state.get("confidence_score")
    if conf is not None:
        lines.append(f"\n【自查结果】")
        lines.append(f"  置信度: {conf}")
        issues = state.get("issues", [])
        if issues:
            lines.append(f"  问题: {'; '.join(str(i) for i in issues[:3])}")
        suggestions = state.get("suggestions", "")
        if suggestions:
            lines.append(f"  建议: {str(suggestions)[:200]}")
    return "\n".join(lines)


# ═══════════════════════ Runner ═══════════════════════

@dataclass
class CaseResult:
    case_id: int; diff: int; desc: str
    score: float = 0.0; details: dict = field(default_factory=dict)
    errors: list = field(default_factory=list); raw: str = ""
    raw_data: dict = field(default_factory=dict)


async def _run_solve(case: dict) -> tuple[str, list[str], dict]:
    """Run SolveAgent for one case, return (output_text, errors, raw_data)."""
    errors = []; output_text = ""; raw_data = {}
    try:
        from app.agents.solve_agent import SolveAgent

        has_api = bool(os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
                       or os.getenv("DASHSCOPE_API_KEY_FLASH") or os.getenv("DEEPSEEK_API_KEY"))

        agent = SolveAgent(use_mock_llm=not has_api)
        state = await agent.run({
            "question": case["question"],
            "context": "",
            "student_profile": {},
        })
        output_text = _fmt_solve(state)
        raw_data = {"steps": state.get("steps", []), "solution": state.get("solution", ""),
                    "confidence_score": state.get("confidence_score"),
                    "issues": state.get("issues", []), "suggestions": state.get("suggestions", "")}
    except Exception as e:
        errors.append(f"{type(e).__name__}: {e}")
        traceback.print_exc()
    return output_text, errors, raw_data


async def run_all() -> list[CaseResult]:
    pipeline_sem = asyncio.Semaphore(PIPELINE_CONCURRENCY)

    # ── Phase 1: 并发跑流水线 ──
    async def phase1(i, case):
        await asyncio.sleep(i * 2.0)
        async with pipeline_sem:
            t0 = time.perf_counter()
            output_text, errors, raw_data = await _run_solve(case)
            elapsed = (time.perf_counter() - t0) * 1000
            return {
                "case": case,
                "output_text": output_text,
                "errors": errors,
                "raw_data": raw_data,
                "pipeline_ms": elapsed,
            }

    print(f"\n  [Phase 1] 并发={PIPELINE_CONCURRENCY} 跑 {len(CASES)} 条 Solve 流水线...\n")
    pipeline_results = list(await asyncio.gather(*[phase1(i, c) for i, c in enumerate(CASES)]))

    # ── Phase 2: 串行 judge ──
    output_path = os.path.join(os.path.dirname(__file__), "_p6_full_output.json")

    print(f"\n  [Phase 2] 串行 judge 评分...\n")
    results = []
    for pr in pipeline_results:
        case = pr["case"]
        t0 = time.perf_counter()
        judge = None
        if pr["output_text"] and not pr["errors"]:
            judge = await _call_judge(case["question"][:300], case["diff"], pr["output_text"])

        score = float(judge["total"]) if judge else 0.0
        elapsed = (time.perf_counter() - t0) * 1000
        details = {"judge_ok": judge is not None, "pipeline_ms": pr["pipeline_ms"]}
        if judge:
            details.update(_jd(judge, elapsed))
        results.append(CaseResult(
            case_id=case["id"], diff=case["diff"], desc=case["desc"],
            score=score, details=details, errors=pr["errors"],
            raw=pr["output_text"][:500],
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
            "question": pr["case"]["question"],
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
    print(f"  P6 Solve 测试报告 (12例)  |  Judge: {JUDGE_MODEL}  |  流水线并发:{PIPELINE_CONCURRENCY} + Judge串行")
    print("=" * 80)

    for r in results:
        d = DIFF.get(r.diff, "???")
        status = "[PASS]" if r.score >= 70 else "[FAIL]"
        print(f"\n  [{r.case_id:2d}] {d} {status} ({r.score:.0f}/100) | {r.desc}")
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
            print(f"       output: {preview}...")

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
    print("  P6 Solve：SolveAgent (Plan → Solve → Review)")
    print("=" * 80)
    await _init_judge()
    print(f"  Judge: {JUDGE_MODEL} (key: ...{_judge_api_key[-4:] if _judge_api_key else 'N/A'})")
    results = await run_all()
    return 0 if report(results) else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
