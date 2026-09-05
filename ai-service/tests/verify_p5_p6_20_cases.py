"""P5+P6 联合测试：20 例真实场景 PlanAgent + SolveAgent

用法:
    cd ai-service && PYTHONPATH=. python tests/verify_p5_p6_20_cases.py

设计:
  - P5 (8 例): PlanCenter 全链路 Goal→Decompose→Schedule
  - P6 (12 例): SolveAgent Plan→Solve→Review
  - 评分: P5→plan_judge, P6→solve_judge
  - 并行: P5+P6 同时跑, 共享 Semaphore(10)
  - 加权总分 > 85 为 PASS，P5×0.4 + P6×0.6
"""
import asyncio, json, os, re, sys, time
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

# ═══════════════════════ Judge 基础设施 ═══════════════════════

_judge_lock = asyncio.Lock()

_plan_llm = None; _plan_sys = ""; _plan_usr = ""
_solve_llm = None; _solve_sys = ""; _solve_usr = ""

MAX_CONCURRENCY = 4
JUDGE_MODEL = os.getenv("MINIMAX_MODEL_REASONER", "MiniMax-M3")
JUDGE_API_KEY = os.getenv("MINIMAX_API_KEY", "")
JUDGE_BASE_URL = os.getenv("MINIMAX_BASE_URL", "")


async def _init_all():
    global _plan_llm, _plan_sys, _plan_usr, _solve_llm, _solve_sys, _solve_usr
    async with _judge_lock:
        if _plan_llm is not None:
            return
        def _make():
            return OpenAILLM(temperature=0.0, max_tokens=512, use_mock=False,
                             model=JUDGE_MODEL, api_key=JUDGE_API_KEY, base_url=JUDGE_BASE_URL)
        _plan_llm = _make()
        _plan_sys = build_prompt("tutor_agent", filename="plan_judge.yaml", key="system")
        _plan_usr = build_prompt("tutor_agent", filename="plan_judge.yaml", key="user")
        _solve_llm = _make()
        _solve_sys = build_prompt("tutor_agent", filename="solve_judge.yaml", key="system")
        _solve_usr = build_prompt("tutor_agent", filename="solve_judge.yaml", key="user")


async def _call_judge(llm, sys_tpl, usr_tpl, question: str, difficulty: int, response: str) -> dict | None:
    truncated = response[:4000]
    user_prompt = interpolate_variables(usr_tpl, {"question": question, "difficulty": str(difficulty), "response": truncated})
    for attempt in range(3):
        try:
            text = await llm.chat([{"role": "user", "content": user_prompt}], system_prompt=sys_tpl)
            text = text.strip()
            if text.startswith("```"): text = re.sub(r"^```(?:json)?\s*", "", text); text = re.sub(r"\s*```$", "", text)
            j = json.loads(text)
            if isinstance(j, dict) and "total" in j:
                return j
            if attempt < 2:
                await asyncio.sleep(1.5)
        except Exception as e:
            if attempt < 2:
                await asyncio.sleep(1.5)
            else:
                logging.getLogger(__name__).warning("Judge failed after 3 attempts: %s", e)
    return None


async def j_plan(q, diff, r): return await _call_judge(_plan_llm, _plan_sys, _plan_usr, q, diff, r)
async def j_solve(q, diff, r): return await _call_judge(_solve_llm, _solve_sys, _solve_usr, q, diff, r)


def _jd(j: dict, elapsed_ms: float) -> dict:
    return {"judge_accuracy": j.get("accuracy",0), "judge_depth": j.get("depth",0),
            "judge_helpfulness": j.get("helpfulness",0), "judge_structure": j.get("structure",0),
            "judge_domain_fit": j.get("domain_fit",0), "judge_total": j.get("total",0),
            "judge_brief": j.get("brief",""), "elapsed_ms": round(elapsed_ms,1)}


# ═══════════════════════ P5 测试用例 (8 例，由难到易) ═══════════════════════

P5_CASES = [
    {
        "id": 1, "difficulty": 3,
        "input": "三个月准备大厂ML面试，已有两年Python经验，数学基础不错（考研数学135），每天能投入4小时。"
                "希望覆盖：机器学习基础算法、深度学习、以及一些ML系统设计的知识。",
        "desc": "高阶面试备战：有经验+强数学+时间充裕+多领域",
    },
    {
        "id": 2, "difficulty": 3,
        "input": "想用AI做量化交易策略。目前情况：Python熟练但金融和ML都是半吊子——"
                "上过一门金融入门课、用sklearn做过简单分类。不知道从哪里系统学。",
        "desc": "交叉学科模糊目标：量化+ML，两方向都不精",
    },
    {
        "id": 3, "difficulty": 2,
        "input": "下个月想入门NLP，之前做过图像分类（用ResNet微调过）。"
                "数学还行，每周能投入15小时左右。",
        "desc": "有一定ML基础转NLP：有CV实战+时间明确",
    },
    {
        "id": 4, "difficulty": 2,
        "input": "毕业论文要写图神经网络方面的，但我GNN零基础。"
                "三个月时间，每天大概3小时，希望能从入门到能复现论文。",
        "desc": "学术方向：GNN零基础+明确时间+写论文目标",
    },
    {
        "id": 5, "difficulty": 2,
        "input": "两周内学会用sklearn做分类和回归，要能独立完成一个简单的预测项目。"
                "有Python基础但没做过ML，每天1.5小时。",
        "desc": "短期实操目标：具体工具+有时间限制+有基础",
    },
    {
        "id": 6, "difficulty": 1,
        "input": "刚学完Python基础（列表、字典、函数、类），"
                "下一步该学什么来入门AI？每天大概2小时。",
        "desc": "入门转折点：有编程基础但不知方向",
    },
    {
        "id": 7, "difficulty": 1,
        "input": "每天只有1小时学AI，帮我安排一周的学习计划。"
                "目前零基础，想看看AI是什么。",
        "desc": "极简微计划：零基础+极短时间+探索性",
    },
    {
        "id": 8, "difficulty": 1,
        "input": "帮我制定一个机器学习入门学习计划。",
        "desc": "一句话请求：无任何背景信息",
    },
]


# ═══════════════════════ P6 测试用例 (12 例，由难到易) ═══════════════════════

P6_CASES = [
    {
        "id": 9, "difficulty": 3,
        "question": "请推导SVM的对偶问题，从原始优化问题出发，"
                    "写出拉格朗日函数、对偶函数、以及对偶问题的最终形式，并解释为什么对偶形式适合引入核函数。",
        "desc": "SVM对偶推导：多步公式+核技巧原理",
    },
    {
        "id": 10, "difficulty": 3,
        "question": "我训练了一个ResNet-18做10分类，训练集accuracy 98%但验证集一直在50%左右徘徊。"
                    "学习率0.1，batch_size=128，用了SGD+momentum。请分析可能的原因并给出诊断步骤。",
        "desc": "训练调试：严重过拟合+架构选择+超参分析",
    },
    {
        "id": 11, "difficulty": 3,
        "question": "给定数据点：[(1, 1.8), (2, 4.2), (3, 5.8), (4, 8.1), (5, 9.9)]。"
                    "请用最小二乘法求线性拟合 y=ax+b，写出正规方程过程并计算R²。",
        "desc": "数值计算：最小二乘法+矩阵运算+R²",
    },
    {
        "id": 12, "difficulty": 3,
        "question": "请详细推导神经网络中反向传播算法：对于一个三层全连接网络（输入d维、"
                    "隐层h维、输出k维，均用sigmoid激活，损失用MSE），推导损失对第二层权重W^(2)的梯度公式。",
        "desc": "反向传播推导：链式法则+矩阵微积分",
    },
    {
        "id": 13, "difficulty": 2,
        "question": "Batch Normalization和Layer Normalization有什么区别？"
                    "分别在什么场景下更适用？为什么Transformer用LayerNorm而CNN用BatchNorm？",
        "desc": "概念辨析：BN vs LN+使用场景+架构适配",
    },
    {
        "id": 14, "difficulty": 2,
        "question": "请解释Transformer中Multi-Head Attention的完整计算过程，"
                    "包括Q、K、V的来源、缩放因子的作用、以及多头拼接后的处理。",
        "desc": "注意力机制：QKV+缩放+多头+线性投影",
    },
    {
        "id": 15, "difficulty": 2,
        "question": "为什么分类任务用交叉熵损失而不用MSE？请从梯度角度详细解释，"
                    "并推导sigmoid输出层下两种损失的梯度公式对比。",
        "desc": "损失函数对比：梯度消失+收敛速度+推导",
    },
    {
        "id": 16, "difficulty": 2,
        "question": "L1正则化和L2正则化有什么区别？为什么L1正则化倾向于产生稀疏解而L2不会？"
                    "请从几何直观和数学推导两个角度解释。",
        "desc": "正则化对比：稀疏性+几何直观+优化角度",
    },
    {
        "id": 17, "difficulty": 1,
        "question": "什么是过拟合？有哪些常见的判断方法和预防手段？",
        "desc": "基础概念：过拟合定义+判断+预防",
    },
    {
        "id": 18, "difficulty": 1,
        "question": "已知参数向量 w=[2.0, 1.5]，学习率 α=0.01，当前梯度 ∇L=[0.5, -0.3]。"
                    "请计算一步梯度下降后的参数值，并解释梯度方向与更新方向的关系。",
        "desc": "基础计算：梯度下降一步更新+方向解释",
    },
    {
        "id": 19, "difficulty": 1,
        "question": "什么是反向传播？请用通俗易懂的语言解释它的基本思想，"
                    "不需要公式，让零基础的人也能理解。",
        "desc": "零基础解释：反向传播直觉+无公式要求",
    },
    {
        "id": 20, "difficulty": 1,
        "question": "梯度下降（GD）和随机梯度下降（SGD）有什么区别？各有什么优缺点？",
        "desc": "基础对比：GD vs SGD定义+优缺点",
    },
]


# ═══════════════════════ 格式化函数 ═══════════════════════

def _fmt_plan(result: dict, student_input: str) -> str:
    lines = [f"学生需求: {student_input}"]
    goal = result.get("goal", {})
    if goal:
        lines.append(f"\n【目标提取】")
        lines.append(f"  标题: {goal.get('goal_title', '')}")
        lines.append(f"  主题: {goal.get('target_topic', '')}")
        lines.append(f"  层级: {goal.get('target_level', '')}")
        lines.append(f"  截止: {goal.get('deadline', '') or '未指定'}")
        lines.append(f"  约束: {', '.join(goal.get('constraints', [])) or '无'}")
    decomp = result.get("decomposition", {})
    if decomp:
        lines.append(f"\n【知识点拆解】")
        macros = decomp.get("macro_topics", [])
        micros = decomp.get("micro_skills", [])
        prereqs = decomp.get("prerequisites", [])
        lines.append(f"  宏观主题 ({len(macros)}): {', '.join(m.get('name','') for m in macros[:7])}")
        lines.append(f"  微观技能 ({len(micros)}): {', '.join(m.get('name','') for m in micros[:10])}")
        lines.append(f"  前置知识 ({len(prereqs)}): {', '.join(p.get('name','') for p in prereqs[:5])}")
        lines.append(f"  概述: {decomp.get('summary', '')}")
    sched = result.get("schedule", {})
    if sched:
        lines.append(f"\n【每日排期】")
        lines.append(f"  标题: {sched.get('plan_title', '')}")
        lines.append(f"  总天数: {sched.get('estimated_days', '?')}")
        lines.append(f"  每日容量: {sched.get('daily_capacity', '?')} 任务")
        steps = sched.get("steps", [])
        for s in steps[:8]:
            lines.append(f"  Day{s.get('day','?')}: [{s.get('type','')}] {s.get('topic','')} ({s.get('bloom_level','')})")
        if len(steps) > 8:
            lines.append(f"  ... 共 {len(steps)} 天")
        lines.append(f"  里程碑: {', '.join(sched.get('milestones', []))}")
    return "\n".join(lines)


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
        lines.append(solution[:1500])
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


# ═══════════════════════ Runners ═══════════════════════

@dataclass
class CaseResult:
    case_id: int; difficulty: int; category: str; message: str; desc: str
    score: float = 0.0; details: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list); raw_output: str = ""


async def run_p5(sem: asyncio.Semaphore) -> list[CaseResult]:
    has_api = bool(os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or os.getenv("DASHSCOPE_API_KEY_FLASH"))

    async def one(case):
        async with sem:
            t0 = time.perf_counter()
            errors = []; plan_text = ""
            try:
                from app.agents.goal_agent import GoalAgent
                from app.agents.decompose_agent import DecomposeAgent
                from app.agents.schedule_agent import ScheduleAgent

                goal_agent = GoalAgent(use_mock_llm=not has_api)
                decompose_agent = DecomposeAgent(use_mock_llm=not has_api)
                schedule_agent = ScheduleAgent(use_mock_llm=not has_api)

                goal_state = await goal_agent.run({
                    "input": case["input"],
                    "context": "",
                    "student_profile": {},
                })
                goal = {
                    "goal_title": goal_state.get("goal_title", case["input"]),
                    "target_topic": goal_state.get("target_topic", case["input"]),
                    "target_level": goal_state.get("target_level", "understand"),
                    "deadline": goal_state.get("deadline", ""),
                    "motivation": goal_state.get("motivation", ""),
                    "constraints": goal_state.get("constraints", []),
                }

                decomp_state = await decompose_agent.run({
                    "topic": goal.get("target_topic", case["input"]),
                    "context": case["input"],
                    "student_profile": {},
                })
                decomp = {
                    "macro_topics": decomp_state.get("macro_topics", []),
                    "micro_skills": decomp_state.get("micro_skills", []),
                    "prerequisites": decomp_state.get("prerequisites", []),
                    "summary": decomp_state.get("summary", ""),
                }

                sched_state = await schedule_agent.run({
                    "goal": goal,
                    "decomposition": decomp,
                    "student_profile": {},
                    "existing_plan": {},
                })
                sched = {
                    "plan_title": sched_state.get("plan_title", ""),
                    "estimated_days": sched_state.get("estimated_days", 0),
                    "daily_capacity": sched_state.get("daily_capacity", 0),
                    "steps": sched_state.get("steps", []),
                    "milestones": sched_state.get("milestones", []),
                }

                result = {"goal": goal, "decomposition": decomp, "schedule": sched}
                plan_text = _fmt_plan(result, case["input"])
            except Exception as e:
                errors.append(str(e))

            judge_result = None
            if plan_text and not errors:
                judge_result = await j_plan(case["input"][:200], case["difficulty"], plan_text)

            score = float(judge_result["total"]) if judge_result else 0.0
            elapsed = (time.perf_counter() - t0) * 1000
            details = {"judge_used": judge_result is not None}
            if judge_result: details.update(_jd(judge_result, elapsed))
            return CaseResult(case_id=case["id"], difficulty=case["difficulty"], category="p5",
                              message=case["input"][:55], desc=case["desc"],
                              score=score, details=details, errors=errors, raw_output=plan_text[:600])

    return list(await asyncio.gather(*[one(c) for c in P5_CASES]))


async def run_p6(sem: asyncio.Semaphore) -> list[CaseResult]:
    has_api = bool(os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or os.getenv("DASHSCOPE_API_KEY_FLASH"))

    async def one(case):
        async with sem:
            t0 = time.perf_counter()
            errors = []; output_text = ""
            try:
                from app.agents.solve_agent import SolveAgent
                agent = SolveAgent(use_mock_llm=not has_api)
                state = await agent.run({
                    "question": case["question"],
                    "context": "",
                    "student_profile": {},
                })
                output_text = _fmt_solve(state)
            except Exception as e:
                errors.append(str(e))

            judge_result = None
            if output_text and not errors:
                judge_result = await j_solve(case["question"][:300], case["difficulty"], output_text)

            score = float(judge_result["total"]) if judge_result else 0.0
            elapsed = (time.perf_counter() - t0) * 1000
            details = {"judge_used": judge_result is not None}
            if judge_result: details.update(_jd(judge_result, elapsed))
            return CaseResult(case_id=case["id"], difficulty=case["difficulty"], category="p6",
                              message=case["question"][:55], desc=case["desc"],
                              score=score, details=details, errors=errors, raw_output=output_text[:600])

    return list(await asyncio.gather(*[one(c) for c in P6_CASES]))


# ═══════════════════════ Report ═══════════════════════

DIFF = {1: "★☆☆", 2: "★★☆", 3: "★★★"}

def report(p5r, p6r):
    all_r = p5r + p6r
    print("\n" + "=" * 90)
    print("  P5+P6 测试报告：Plan (8例) + Solve (12例)")
    print("=" * 90)

    for r in all_r:
        d = DIFF.get(r.difficulty, "???"); cat = {"p5":"P5","p6":"P6"}[r.category]
        status = "[PASS]" if r.score >= 70 else "[FAIL]"
        msg = r.message[:50] + "..." if len(r.message) > 50 else r.message
        print(f"\n  [{r.case_id:2d}] {cat} {d} {status} ({r.score:.1f}/100) | {msg}")
        print(f"       说明: {r.desc}")
        if r.errors:
            for e in r.errors: print(f"       ERROR: {e}")
        j = r.details
        ji = f"A{j.get('judge_accuracy',0)} D{j.get('judge_depth',0)} H{j.get('judge_helpfulness',0)} S{j.get('judge_structure',0)} F{j.get('judge_domain_fit',0)}" if j.get("judge_used") else "(judge 不可用)"
        print(f"       评分: {ji} | brief: {j.get('judge_brief','')}")
        if r.raw_output:
            print(f"       输出: {r.raw_output[:250].replace(chr(10), ' ')}")

    def stats(results, label):
        if not results: return 0.0
        avg = sum(r.score for r in results) / len(results)
        passed = sum(1 for r in results if r.score >= 70)
        st = "[PASS]" if avg >= 70 else "[FAIL]"
        print(f"\n  {label:30s}  avg={avg:.1f} {st}  pass={passed}/{len(results)}")
        return avg

    print("\n" + "-" * 60)
    p5a = stats(p5r, "P5 Plan (8例)")
    p6a = stats(p6r, "P6 Solve (12例)")
    w = p5a * 0.4 + p6a * 0.6
    print(f"  加权 (P5×0.4 + P6×0.6): {w:.1f}  {'[PASS]' if w > 85 else '[FAIL]'}")

    for diff in [1,2,3]:
        dr = [r for r in all_r if r.difficulty == diff]
        if dr:
            avg = sum(r.score for r in dr) / len(dr)
            print(f"    {DIFF[diff]} ({len(dr)}例) avg={avg:.1f}  pass={sum(1 for r in dr if r.score>=70)}/{len(dr)}")
    print("=" * 90)
    return w > 85


# ═══════════════════════ Main ═══════════════════════

async def main():
    print("=" * 90)
    print("  P5+P6：20 例真实场景 PlanAgent + SolveAgent")
    print("=" * 90)

    await _init_all()
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    print("\n  P5 (8例 Plan) + P6 (12例 Solve) 并行跑 [并发=10]...\n")
    p5r, p6r = await asyncio.gather(run_p5(sem), run_p6(sem))

    grand_pass = report(p5r, p6r)
    return 0 if grand_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
