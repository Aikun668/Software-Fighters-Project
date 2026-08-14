"""P2+P3 联合测试 v2：20 例全新用例 ProfileAgent + ExerciseAgent

用法:
    cd ai-service && PYTHONPATH=. python tests/verify_p2_p3_20_cases.py

设计:
  - P2 (8 例): 贴近真实场景的画像提取 — 零基础自述、跨领域转行、模糊表达、多轮渐进
  - P3 (12 例): 练习生成 + 错因分析 — 覆盖不同难度/用途/学科交叉
  - 评分: P2→profile_judge, P3 exercise_gen→exercise_judge, P3 error_analysis→quality_judge
  - 并行: P2+P3 同时跑, 共享 Semaphore(12)
  - 加权总分 > 85 为 PASS
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

from app.services.llm_service import PROFILE_DIRECTOR, OpenAILLM
from app.utils.prompt_loader import interpolate_variables, build_prompt

# ═══════════════════════ Judge 基础设施 ═══════════════════════

_judge_lock = asyncio.Lock()
_judge_cfg = PROFILE_DIRECTOR.default

# quality_judge (P3 error_analysis, 用于评判 TutorAgent 的回答)
_q_llm = None; _q_sys = ""; _q_usr = ""
# profile_judge (P2 画像提取)
_p_llm = None; _p_sys = ""; _p_usr = ""
# exercise_judge (P3 exercise_gen 出题)
_e_llm = None; _e_sys = ""; _e_usr = ""

MAX_CONCURRENCY = 12


async def _init_all():
    global _q_llm, _q_sys, _q_usr, _p_llm, _p_sys, _p_usr, _e_llm, _e_sys, _e_usr
    async with _judge_lock:
        if _q_llm is not None:
            return
        c = _judge_cfg
        def _make(**kw):
            return OpenAILLM(temperature=c.temperature, max_tokens=512, use_mock=False, model=c.model, api_key=c.api_key, base_url=c.base_url, **kw)
        _q_llm = _make(); _q_sys = build_prompt("tutor_agent", filename="quality_judge.yaml", key="system"); _q_usr = build_prompt("tutor_agent", filename="quality_judge.yaml", key="user")
        _p_llm = _make(); _p_sys = build_prompt("tutor_agent", filename="profile_judge.yaml", key="system"); _p_usr = build_prompt("tutor_agent", filename="profile_judge.yaml", key="user")
        _e_llm = _make(); _e_sys = build_prompt("tutor_agent", filename="exercise_judge.yaml", key="system"); _e_usr = build_prompt("tutor_agent", filename="exercise_judge.yaml", key="user")


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


async def j_profile(q, diff, r): return await _call_judge(_p_llm, _p_sys, _p_usr, q, diff, r)
async def j_exercise(q, diff, r): return await _call_judge(_e_llm, _e_sys, _e_usr, q, diff, r)
async def j_quality(q, diff, r): return await _call_judge(_q_llm, _q_sys, _q_usr, q, diff, r)


def _jd(j: dict, elapsed_ms: float) -> dict:
    return {"judge_accuracy": j.get("accuracy",0), "judge_depth": j.get("depth",0),
            "judge_helpfulness": j.get("helpfulness",0), "judge_structure": j.get("structure",0),
            "judge_domain_fit": j.get("domain_fit",0), "judge_total": j.get("total",0),
            "judge_brief": j.get("brief",""), "elapsed_ms": round(elapsed_ms,1)}


# ═══════════════════════ P2 测试用例 (8 例) ═══════════════════════

P2_CASES = [
    # ── 贴近真实场景 ──
    {
        "id": 1, "difficulty": 1,
        "messages": [
            {"role": "user", "content": "老师好，我是生物专业的大三学生，这学期选了人工智能导论课。"},
            {"role": "user", "content": "编程零基础，数学也只学过基础高数，现在很慌不知道能不能跟上。"}
        ],
        "desc": "零基础自述：非CS背景+编程零基础+数学弱+焦虑",
        "check_dims": ["knowledge_base", "learning_goal", "weak_points"],
    },
    {
        "id": 2, "difficulty": 1,
        "messages": [
            {"role": "user", "content": "我之前在字节跳动做了两年数据分析，SQL和Python都熟练。"},
            {"role": "user", "content": "现在想转AI方向，先从机器学习开始系统学。"}
        ],
        "desc": "转行选手：有数据分析经验+编程熟+目标明确",
        "check_dims": ["knowledge_base", "learning_goal", "interest_direction"],
    },
    {
        "id": 3, "difficulty": 2,
        "messages": [
            {"role": "user", "content": "我大一刚学完C语言，成绩还行。对深度学习很感兴趣但不知道怎么入门，"},
            {"role": "user", "content": "听说要学很多数学，有点害怕。每天能挤出3小时学习。"}
        ],
        "desc": "大学新生：有编程入门+对DL感兴趣+时间受限+数学恐惧",
        "check_dims": ["knowledge_base", "interest_direction", "learning_pace", "weak_points"],
    },
    {
        "id": 4, "difficulty": 2,
        "messages": [
            {"role": "user", "content": "我在Kaggle上打过几个比赛，用过XGBoost和LightGBM，但对原理一知半解。"},
            {"role": "user", "content": "想把基础补扎实，特别是树模型的数学原理。"},
            {"role": "assistant", "content": "你的实践经验很丰富！我们来看看决策树的划分原理..."},
            {"role": "user", "content": "对，我就是ID3、C4.5、CART这些算法的区别搞不清楚。"}
        ],
        "desc": "实践先行者：有Kaggle经验但不扎实，多轮补充细节",
        "check_dims": ["knowledge_base", "weak_points", "interest_direction"],
    },
    {
        "id": 5, "difficulty": 2,
        "messages": [
            {"role": "user", "content": "我对计算机视觉和NLP都挺感兴趣的，不知道先学哪个好。"},
            {"role": "user", "content": "数学基础一般，微积分和线代都学过但忘得差不多了。"}
        ],
        "desc": "方向犹豫：多兴趣+选择困难+数学遗忘",
        "check_dims": ["interest_direction", "knowledge_base", "weak_points"],
    },
    {
        "id": 6, "difficulty": 3,
        "messages": [
            {"role": "user", "content": "我的强化学习项目卡住了。环境是自定义的，状态空间连续且维度很高(>100维)，"},
            {"role": "user", "content": "用DQN训练完全不收敛，reward一直在震荡。Action space是离散的但有20个。"}
        ],
        "desc": "高阶求助：RL工程问题+连续高维状态+训练不收敛",
        "check_dims": ["knowledge_base", "weak_points"],
    },
    {
        "id": 7, "difficulty": 3,
        "messages": [
            {"role": "user", "content": "我数理基础很强（数学系本科，实变函数95），去年开始自学ML，"},
            {"role": "user", "content": "今年想冲击顶会论文，主要做diffusion model的理论分析方向。"},
            {"role": "assistant", "content": "你的数学背景对理论分析方向是巨大优势。"},
            {"role": "user", "content": "嗯，我在看SDE和score-based的论文，但Stochastic Differential Equation这块还需要补。"}
        ],
        "desc": "研究型选手：数学系高材生+明确研究方向+自知短板",
        "check_dims": ["knowledge_base", "learning_goal", "weak_points", "interest_direction"],
    },
    {
        "id": 8, "difficulty": 1,
        "messages": [{"role": "user", "content": "推荐几个AI入门教程吧，要免费的。"}],
        "desc": "极简输入：只有一句话，无背景信息",
        "check_dims": ["knowledge_base", "learning_goal"],
    },
]

# ═══════════════════════ P3 测试用例 (12 例) ═══════════════════════

P3_CASES = [
    # ── 出题 (8 例) ──
    {
        "id": 9, "difficulty": 1, "type": "exercise_gen",
        "params": {"topic": "K-means聚类", "count": 3, "difficulty": "easy", "purpose": "warmup_not_exam"},
        "desc": "聚类基础选择题",
    },
    {
        "id": 10, "difficulty": 1, "type": "exercise_gen",
        "params": {"topic": "感知机模型", "count": 2, "difficulty": "easy", "purpose": "warmup_not_exam"},
        "desc": "感知机入门题",
    },
    {
        "id": 11, "difficulty": 2, "type": "exercise_gen",
        "params": {"topic": "PCA主成分分析", "count": 3, "difficulty": "medium", "purpose": "review"},
        "desc": "PCA 复习题：概念+推导",
    },
    {
        "id": 12, "difficulty": 2, "type": "exercise_gen",
        "params": {"topic": "RNN循环神经网络", "count": 3, "difficulty": "medium", "purpose": "new"},
        "desc": "RNN 新课巩固",
    },
    {
        "id": 13, "difficulty": 2, "type": "exercise_gen",
        "params": {"topic": "集成学习 Bagging与Boosting", "count": 4, "difficulty": "medium", "purpose": "weakness"},
        "desc": "集成学习：薄弱点专项",
    },
    {
        "id": 14, "difficulty": 3, "type": "exercise_gen",
        "params": {"topic": "变分自编码器 VAE", "count": 3, "difficulty": "hard", "purpose": "new"},
        "desc": "VAE 高难度生成题",
    },
    {
        "id": 15, "difficulty": 3, "type": "exercise_gen",
        "params": {"topic": "马尔可夫决策过程 MDP", "count": 3, "difficulty": "hard", "purpose": "review"},
        "desc": "MDP 强化学习基础推导题",
    },
    {
        "id": 16, "difficulty": 3, "type": "exercise_gen",
        "params": {"topic": "对比学习 Contrastive Learning", "count": 3, "difficulty": "hard", "purpose": "new"},
        "desc": "对比学习前沿题",
    },
    # ── 错因分析 (4 例) ──
    {
        "id": 17, "difficulty": 2, "type": "error_analysis",
        "question": "什么是过拟合？怎样判断模型是否过拟合了？",
        "student_answer": "过拟合就是模型在训练集上准确率很高但在测试集上很低。可以通过看训练集和测试集的准确率差距来判断，差距大就过拟合了。",
        "desc": "过拟合的深层原因未解释（只说了现象没讲原理）",
    },
    {
        "id": 18, "difficulty": 2, "type": "error_analysis",
        "question": "推导逻辑回归的损失函数。",
        "student_answer": "逻辑回归用交叉熵损失：L = -[y*log(p) + (1-y)*log(1-p)]。因为如果用MSE会有很多局部最优。",
        "desc": "逻辑回归推导缺失：跳跃到结论无过程",
    },
    {
        "id": 19, "difficulty": 3, "type": "error_analysis",
        "question": "请解释Transformer中的自注意力机制（Self-Attention）的计算过程。",
        "student_answer": "自注意力就是每个词和所有其他词计算相关性，Query和Key做点积，然后softmax得到权重，再乘以Value得到输出。多头注意力就是做多次然后拼接。",
        "desc": "Transformer注意力：缺少QKV来源、缩放因子、矩阵维度说明",
    },
    {
        "id": 20, "difficulty": 3, "type": "error_analysis",
        "question": "请解释为什么深度神经网络中会出现梯度消失问题，以及如何缓解。",
        "student_answer": "梯度消失是因为反向传播时连乘导致梯度越来越小。解决方法是用ReLU激活函数代替Sigmoid，因为ReLU的导数恒为1不会缩小。",
        "desc": "梯度消失：ReLU导数描述错误（不是恒为1）+方案不完整",
    },
]


# ═══════════════════════ 格式化函数 ═══════════════════════

def _fmt_profile(profile: dict, check_dims: list[str], reasoning: str = "") -> str:
    labels = {"knowledge_base": "知识基础", "cognitive_style": "学习风格",
              "learning_goal": "学习目标", "weak_points": "薄弱环节",
              "learning_pace": "学习节奏", "interest_direction": "兴趣方向"}
    lines = []
    if reasoning:
        lines.append(f"【提取依据】{reasoning}")
    lines.append("【提取的画像维度】")
    for dim in check_dims:
        val = profile.get(dim)
        label = labels.get(dim, dim)
        if val is None or val == [] or val == "":
            lines.append(f"  {label}: (未提取到)")
        elif isinstance(val, list):
            items = ["; ".join(f"{x.get('content', str(x))}" if isinstance(x, dict) else str(x) for x in val[:5])]
            lines.append(f"  {label}: {items[0]}")
        elif isinstance(val, (int, float)):
            lines.append(f"  {label}: {val}/100")
        else:
            lines.append(f"  {label}: {val}")
    return "\n".join(lines)


def _fmt_exercises(params: dict, questions: list) -> str:
    lines = [f"出题要求: 主题={params['topic']}, 难度={params['difficulty']}, "
             f"数量={params['count']}, 用途={params.get('purpose','')}",
             f"实际生成 {len(questions)} 道题:"]
    for i, q in enumerate(questions, 1):
        if isinstance(q, dict):
            qt = q.get("type", q.get("question_type", "?"))
            qt_text = q.get("question", q.get("content", str(q)))
            lines.append(f"\n  [{i}] 题型={qt}")
            lines.append(f"  题目: {qt_text}")
            opts = q.get("options")
            if opts:
                if isinstance(opts, dict):
                    lines.append(f"  选项: {', '.join(f'{k}. {v}' for k, v in opts.items())}")
                else:
                    lines.append(f"  选项: {opts}")
            ans = q.get("correct_answer", q.get("answer", ""))
            if ans:
                lines.append(f"  正确答案: {str(ans)[:300]}")
            expl = q.get("explanation", "")
            if expl:
                lines.append(f"  解析: {str(expl)[:300]}")
        else:
            lines.append(f"  [{i}] {str(q)[:300]}")
    return "\n".join(lines)


# ═══════════════════════ Runners ═══════════════════════

@dataclass
class CaseResult:
    case_id: int; difficulty: int; category: str; message: str; desc: str
    score: float = 0.0; details: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list); raw_output: str = ""


async def run_p2(sem: asyncio.Semaphore) -> list[CaseResult]:
    from app.agents.profile_agent import ProfileAgent
    has_api = bool(os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or os.getenv("DASHSCOPE_API_KEY_FLASH"))

    async def one(case):
        async with sem:
            t0 = time.perf_counter()
            errors = []; profile = {}; reasoning = ""
            try:
                agent = ProfileAgent(use_mock_llm=not has_api)
                result = await agent.extract_and_merge(profile_dict={}, messages=case["messages"])
                profile = result.get("profile", {})
                reasoning = result.get("reasoning", "")
            except Exception as e:
                errors.append(str(e))

            profile_text = _fmt_profile(profile, case["check_dims"], reasoning)
            user_msgs = " | ".join(m["content"][:80] for m in case["messages"] if m["role"] == "user")
            judge_result = None
            if profile_text and not errors:
                judge_result = await j_profile(user_msgs, case["difficulty"], profile_text)

            score = float(judge_result["total"]) if judge_result else 0.0
            elapsed = (time.perf_counter() - t0) * 1000
            details = {"judge_used": judge_result is not None}
            if judge_result: details.update(_jd(judge_result, elapsed))
            return CaseResult(case_id=case["id"], difficulty=case["difficulty"], category="p2",
                              message=case["messages"][0]["content"][:55], desc=case["desc"],
                              score=score, details=details, errors=errors, raw_output=profile_text[:300])

    return list(await asyncio.gather(*[one(c) for c in P2_CASES]))


async def run_p3(sem: asyncio.Semaphore) -> list[CaseResult]:
    has_api = bool(os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or os.getenv("DASHSCOPE_API_KEY_FLASH"))

    async def one(case):
        async with sem:
            t0 = time.perf_counter()
            errors = []; output_text = ""

            if case["type"] == "exercise_gen":
                try:
                    from app.agents.exercise_agent import ExerciseAgent
                    agent = ExerciseAgent(use_mock_llm=not has_api)
                    state = await agent.run({**case["params"], "student_profile": {}})
                    questions = state.get("questions", [])
                    output_text = _fmt_exercises(case["params"], questions)
                except Exception as e:
                    errors.append(str(e))

                judge_result = None
                if output_text and not errors:
                    p = case["params"]
                    jq = f"主题={p['topic']}, 难度={p['difficulty']}, 数量={p['count']}, 用途={p.get('purpose','')}"
                    judge_result = await j_exercise(jq, case["difficulty"], output_text)

            else:  # error_analysis
                try:
                    from app.agents.tutor_agent import TutorAgent
                    agent = TutorAgent(use_mock_llm=not has_api)
                    analysis_prompt = (f"题目：{case['question']}\n\n学生答案：{case['student_answer']}\n\n"
                                       f"请分析学生的错误原因，指出具体哪里理解有误，并给出正确解法和学习建议。")
                    state = await agent.run({"messages": [{"role": "user", "content": analysis_prompt}],
                                             "user_id": 1, "student_profile": {}, "course_id": "AI101"})
                    output_text = state.get("response", "")
                except Exception as e:
                    errors.append(str(e))

                judge_result = None
                if output_text and not errors:
                    judge_result = await j_quality(case["question"], case["difficulty"], output_text)

            score = float(judge_result["total"]) if judge_result else 0.0
            elapsed = (time.perf_counter() - t0) * 1000
            details = {"judge_used": judge_result is not None}
            if judge_result: details.update(_jd(judge_result, elapsed))
            return CaseResult(case_id=case["id"], difficulty=case["difficulty"], category="p3",
                              message=case.get("question", case["desc"])[:55], desc=case["desc"],
                              score=score, details=details, errors=errors, raw_output=output_text[:600])

    return list(await asyncio.gather(*[one(c) for c in P3_CASES]))


# ═══════════════════════ Report ═══════════════════════

DIFF = {1: "★☆☆", 2: "★★☆", 3: "★★★"}

def report(p2r, p3r):
    all_r = p2r + p3r
    print("\n" + "=" * 90)
    print("  P2+P3 v2 测试报告")
    print("=" * 90)

    for r in all_r:
        d = DIFF.get(r.difficulty, "???"); cat = {"p2":"P2","p3":"P3"}[r.category]
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
            print(f"       输出: {r.raw_output[:200].replace(chr(10), ' ')}")

    def stats(results, label):
        if not results: return 0.0
        avg = sum(r.score for r in results) / len(results)
        passed = sum(1 for r in results if r.score >= 70)
        st = "[PASS]" if avg >= 70 else "[FAIL]"
        print(f"\n  {label:30s}  avg={avg:.1f} {st}  pass={passed}/{len(results)}")
        return avg

    print("\n" + "-" * 60)
    p2a = stats(p2r, "P2 ProfileAgent (8例)")
    p3a = stats(p3r, "P3 ExerciseAgent (12例)")
    w = p2a * 0.4 + p3a * 0.6
    print(f"  加权 (P2×0.4 + P3×0.6): {w:.1f}  {'[PASS]' if w > 85 else '[FAIL]'}")

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
    print("  P2+P3 v2：20 例全新用例 ProfileAgent + ExerciseAgent")
    print("=" * 90)

    await _init_all()
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    print("\n  P2 (8例) + P3 (12例) 并行跑 [并发=12]...\n")
    p2r, p3r = await asyncio.gather(run_p2(sem), run_p3(sem))

    grand_pass = report(p2r, p3r)
    return 0 if grand_pass else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
