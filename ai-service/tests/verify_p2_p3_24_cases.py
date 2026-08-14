"""P2+P3 联合测试：ProfileAgent + ExerciseAgent 24 例验证测试。

用法:
    cd ai-service && PYTHONPATH=. python tests/verify_p2_p3_24_cases.py

设计:
  - P2 (10 例): ProfileAgent 画像提取 → flash LLM 评估提取准确性
  - P3 (14 例): ExerciseAgent 出题 + 错因分析 → flash LLM 评估质量
  - 评分: 全部 LLM-as-Judge 五维评分
  - 加权总分 > 85 为 PASS
"""
import asyncio
import json
import os
import re
import sys
import time
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

# ═══════════════════════════════════════════════════════════════════════════
# Judge 基础设施
# ═══════════════════════════════════════════════════════════════════════════

_judge_llm = None
_judge_system_template: str = ""
_judge_user_template: str = ""
_judge_lock = asyncio.Lock()

_profile_judge_llm = None
_profile_judge_system: str = ""
_profile_judge_user: str = ""

_exercise_judge_llm = None
_exercise_judge_system: str = ""
_exercise_judge_user: str = ""

MAX_CONCURRENCY = 12


async def _init_judge():
    global _judge_llm, _judge_system_template, _judge_user_template
    async with _judge_lock:
        if _judge_llm is not None:
            return
        cfg = PROFILE_DIRECTOR.default
        _judge_llm = OpenAILLM(
            temperature=cfg.temperature, max_tokens=512, use_mock=False,
            model=cfg.model, api_key=cfg.api_key, base_url=cfg.base_url,
        )
        _judge_system_template = build_prompt(
            "tutor_agent", filename="quality_judge.yaml", key="system",
        )
        _judge_user_template = build_prompt(
            "tutor_agent", filename="quality_judge.yaml", key="user",
        )


async def _init_profile_judge():
    global _profile_judge_llm, _profile_judge_system, _profile_judge_user
    async with _judge_lock:
        if _profile_judge_llm is not None:
            return
        cfg = PROFILE_DIRECTOR.default
        _profile_judge_llm = OpenAILLM(
            temperature=cfg.temperature, max_tokens=512, use_mock=False,
            model=cfg.model, api_key=cfg.api_key, base_url=cfg.base_url,
        )
        _profile_judge_system = build_prompt(
            "tutor_agent", filename="profile_judge.yaml", key="system",
        )
        _profile_judge_user = build_prompt(
            "tutor_agent", filename="profile_judge.yaml", key="user",
        )


async def _init_exercise_judge():
    global _exercise_judge_llm, _exercise_judge_system, _exercise_judge_user
    async with _judge_lock:
        if _exercise_judge_llm is not None:
            return
        cfg = PROFILE_DIRECTOR.default
        _exercise_judge_llm = OpenAILLM(
            temperature=cfg.temperature, max_tokens=512, use_mock=False,
            model=cfg.model, api_key=cfg.api_key, base_url=cfg.base_url,
        )
        _exercise_judge_system = build_prompt(
            "tutor_agent", filename="exercise_judge.yaml", key="system",
        )
        _exercise_judge_user = build_prompt(
            "tutor_agent", filename="exercise_judge.yaml", key="user",
        )


async def _call_judge(llm, system_template, user_template,
                      question: str, difficulty: int, response: str) -> dict | None:
    truncated = response[:2800]
    user_prompt = interpolate_variables(
        user_template,
        {"question": question, "difficulty": str(difficulty), "response": truncated},
    )
    try:
        result_text = await llm.chat(
            [{"role": "user", "content": user_prompt}],
            system_prompt=system_template,
        )
        text = result_text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        judge_result = json.loads(text)
        if not isinstance(judge_result, dict) or "total" not in judge_result:
            return None
        return judge_result
    except Exception as e:
        logging.getLogger(__name__).warning("Judge failed: %s", e)
        return None


async def judge_quality(question: str, difficulty: int, response: str) -> dict | None:
    global _judge_llm
    if _judge_llm is None:
        try:
            await _init_judge()
        except Exception as e:
            logging.getLogger(__name__).warning("Judge init failed: %s", e)
            return None
    return await _call_judge(
        _judge_llm, _judge_system_template, _judge_user_template,
        question, difficulty, response,
    )


async def judge_profile_quality(question: str, difficulty: int, response: str) -> dict | None:
    global _profile_judge_llm
    if _profile_judge_llm is None:
        try:
            await _init_profile_judge()
        except Exception as e:
            logging.getLogger(__name__).warning("Profile judge init failed: %s", e)
            return None
    return await _call_judge(
        _profile_judge_llm, _profile_judge_system, _profile_judge_user,
        question, difficulty, response,
    )


async def judge_exercise_quality(question: str, difficulty: int, response: str) -> dict | None:
    global _exercise_judge_llm
    if _exercise_judge_llm is None:
        try:
            await _init_exercise_judge()
        except Exception as e:
            logging.getLogger(__name__).warning("Exercise judge init failed: %s", e)
            return None
    return await _call_judge(
        _exercise_judge_llm, _exercise_judge_system, _exercise_judge_user,
        question, difficulty, response,
    )


def _j_details(j: dict, elapsed_ms: float) -> dict:
    return {
        "judge_accuracy": j.get("accuracy", 0), "judge_depth": j.get("depth", 0),
        "judge_helpfulness": j.get("helpfulness", 0), "judge_structure": j.get("structure", 0),
        "judge_domain_fit": j.get("domain_fit", 0), "judge_total": j.get("total", 0),
        "judge_brief": j.get("brief", ""), "elapsed_ms": round(elapsed_ms, 1),
    }


# ═══════════════════════════════════════════════════════════════════════════
# P2 ProfileAgent 测试用例 (10 例)
# ═══════════════════════════════════════════════════════════════════════════

P2_CASES = [
    # ── ★☆☆ 单维度提取 (6 例) ──
    {
        "id": 1, "difficulty": 1,
        "messages": [{"role": "user", "content": "我数学基础不错，高考数学140分，大学高数90分"}],
        "desc": "knowledge_base 数值提取",
        "check_dims": ["knowledge_base"],
    },
    {
        "id": 2, "difficulty": 1,
        "messages": [{"role": "user", "content": "我比较喜欢看视频教程学习，不太爱看教材和文档"}],
        "desc": "cognitive_style 枚举提取",
        "check_dims": ["cognitive_style"],
    },
    {
        "id": 3, "difficulty": 1,
        "messages": [{"role": "user", "content": "我想学机器学习，以后打算做算法工程师"}],
        "desc": "learning_goal 目标提取",
        "check_dims": ["learning_goal"],
    },
    {
        "id": 4, "difficulty": 1,
        "messages": [{"role": "user", "content": "我对自然语言处理NLP特别感兴趣，尤其是文本生成方向"}],
        "desc": "interest_direction 兴趣提取",
        "check_dims": ["interest_direction"],
    },
    {
        "id": 5, "difficulty": 1,
        "messages": [{"role": "user", "content": "我卷积神经网络这章学得不好，卷积和池化的概念总搞混"}],
        "desc": "weak_points 薄弱点提取",
        "check_dims": ["weak_points"],
    },
    {
        "id": 6, "difficulty": 1,
        "messages": [{"role": "user", "content": "我每天大概能学2小时，周末可以多一些，希望稳步推进不急躁"}],
        "desc": "learning_pace 学习节奏提取",
        "check_dims": ["learning_pace"],
    },
    # ── ★★☆ 多维度 + 增量 (2 例) ──
    {
        "id": 7, "difficulty": 2,
        "messages": [{"role": "user", "content": "我Python编程基础还行但数学比较弱，想学深度学习做计算机视觉方向，每周大概能投入15小时"}],
        "desc": "单条消息多维提取（knowledge_base + learning_goal + interest + pace）",
        "check_dims": ["knowledge_base", "learning_goal", "interest_direction", "learning_pace"],
    },
    {
        "id": 8, "difficulty": 2,
        "messages": [
            {"role": "user", "content": "我反向传播这块不太懂，梯度计算总是出错"},
            {"role": "assistant", "content": "我来帮你理清反向传播的思路..."},
            {"role": "user", "content": "还有激活函数的选择我也不太确定，Sigmoid和ReLU什么时候用哪个？"},
        ],
        "desc": "多轮对话增量提取 weak_points",
        "check_dims": ["weak_points"],
    },
    # ── ★★★ 冲突 + 去重 (2 例) ──
    {
        "id": 9, "difficulty": 3,
        "messages": [
            {"role": "user", "content": "我数学基础很好，高中数学竞赛拿过奖"},
            {"role": "assistant", "content": "了解了！"},
            {"role": "user", "content": "其实我大学高数挂过科，数学基础挺差的"},
        ],
        "desc": "矛盾信息→stability_counter 冲突处理",
        "check_dims": ["knowledge_base"],
    },
    {
        "id": 10, "difficulty": 3,
        "messages": [
            {"role": "user", "content": "我梯度下降理解得不够深入"},
            {"role": "assistant", "content": "我记下了。"},
            {"role": "user", "content": "还有就是我梯度下降这块掌握得不好，总是出错"},
        ],
        "desc": "相似 weak_point 两次→semantic_judge 去重",
        "check_dims": ["weak_points"],
    },
]

# ═══════════════════════════════════════════════════════════════════════════
# P3 ExerciseAgent 测试用例 (14 例)
# ═══════════════════════════════════════════════════════════════════════════

P3_CASES = [
    # ── ★☆☆ 基础出题 (3 例) ──
    {
        "id": 11, "difficulty": 1,
        "type": "exercise_gen",
        "params": {"topic": "决策树", "count": 3, "difficulty": "easy", "purpose": "warmup_not_exam"},
        "desc": "基础出题：决策树选择题",
    },
    {
        "id": 12, "difficulty": 1,
        "type": "exercise_gen",
        "params": {"topic": "线性回归", "count": 2, "difficulty": "easy", "purpose": "warmup_not_exam"},
        "desc": "基础出题：线性回归计算题",
    },
    {
        "id": 13, "difficulty": 1,
        "type": "exercise_gen",
        "params": {"topic": "过拟合与正则化", "count": 3, "difficulty": "easy", "purpose": "warmup_not_exam"},
        "desc": "基础出题：过拟合概念题",
    },
    # ── ★★☆ 定向出题 (4 例) ──
    {
        "id": 14, "difficulty": 2,
        "type": "exercise_gen",
        "params": {"topic": "CNN卷积神经网络", "count": 3, "difficulty": "medium", "purpose": "review"},
        "desc": "中等难度：CNN 问答题",
    },
    {
        "id": 15, "difficulty": 2,
        "type": "exercise_gen",
        "params": {"topic": "梯度下降", "count": 5, "difficulty": "medium", "purpose": "weakness"},
        "desc": "薄弱点针对性出题",
    },
    {
        "id": 16, "difficulty": 2,
        "type": "exercise_gen",
        "params": {"topic": "LSTM循环神经网络", "count": 3, "difficulty": "medium", "purpose": "new"},
        "desc": "新课内容出题",
    },
    {
        "id": 17, "difficulty": 2,
        "type": "exercise_gen",
        "params": {"topic": "支持向量机SVM", "count": 4, "difficulty": "medium", "purpose": "review"},
        "desc": "中等难度：SVM 概念+计算混合",
    },
    # ── ★★★ 高难度出题 (3 例) ──
    {
        "id": 18, "difficulty": 3,
        "type": "exercise_gen",
        "params": {"topic": "Transformer注意力机制", "count": 4, "difficulty": "hard", "purpose": "review"},
        "desc": "高难度：Transformer 综合题",
    },
    {
        "id": 19, "difficulty": 3,
        "type": "exercise_gen",
        "params": {"topic": "GAN生成对抗网络", "count": 3, "difficulty": "hard", "purpose": "new"},
        "desc": "高难度：GAN 原理+推导题",
    },
    {
        "id": 20, "difficulty": 3,
        "type": "exercise_gen",
        "params": {"topic": "强化学习Q-Learning", "count": 3, "difficulty": "hard", "purpose": "review"},
        "desc": "高难度：强化学习数学推导",
    },
    # ── ★★☆ 错因分析 (2 例) ──
    {
        "id": 21, "difficulty": 2,
        "type": "error_analysis",
        "question": "请解释精确率（Precision）和召回率（Recall）的区别，并说明各自适合什么场景。",
        "student_answer": "精确率是预测为正的里面有多少真的是正，召回率是真的是正的里面有多少被预测为正。精确率适合不想漏掉正例的场景，召回率适合不想误判的场景。",
        "desc": "错因分析：精确率/召回率概念混淆",
    },
    {
        "id": 22, "difficulty": 2,
        "type": "error_analysis",
        "question": "用梯度下降求 f(x) = x² + 3x + 2 的最小值点，假设起始点 x₀=5，学习率 α=0.1，迭代 3 步。",
        "student_answer": "f'(x)=2x+3。第1步：x₁=5-0.1×(2×5+3)=5-1.3=3.7。第2步：x₂=3.7-0.1×(2×3.7+3)=3.7-1.04=2.66。第3步：x₃=2.66-0.1×(2×2.66+3)=2.66-0.832=1.828。最小值点是 x=1.828。",
        "desc": "错因分析：梯度下降计算检查",
    },
    # ── ★★★ 深度错因分析 (2 例) ──
    {
        "id": 23, "difficulty": 3,
        "type": "error_analysis",
        "question": "解释偏差（Bias）和方差（Variance）的权衡关系。为什么模型复杂度增加时，偏差减小但方差增大？",
        "student_answer": "偏差是模型预测值和真实值之间的差距，方差是模型在不同训练集上的预测变化。简单模型偏差大方差小，复杂模型偏差小方差大。因为复杂模型容易过拟合训练数据，所以方差大。",
        "desc": "错因分析：bias-variance 理解深度不足",
    },
    {
        "id": 24, "difficulty": 3,
        "type": "error_analysis",
        "question": "设计一个用于MNIST手写数字识别的CNN网络结构，说明每层的参数和输出尺寸。输入为28×28灰度图。",
        "student_answer": "第一层卷积32个3×3滤波器，输出26×26×32。第二层卷积64个3×3滤波器，输出24×24×64。全连接层128个神经元，输出128。最后全连接层10个神经元输出10类。",
        "desc": "错因分析：CNN架构设计遗漏（缺池化层/激活函数）",
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# Scoring
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class CaseResult:
    case_id: int
    difficulty: int
    category: str
    message: str
    desc: str
    score: float = 0.0
    details: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    raw_output: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# P2 ProfileAgent Runner
# ═══════════════════════════════════════════════════════════════════════════

async def run_p2_tests(semaphore: asyncio.Semaphore) -> list[CaseResult]:
    from app.agents.profile_agent import ProfileAgent

    has_api = bool(os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
                   or os.getenv("DASHSCOPE_API_KEY_FLASH"))

    async def run_one(case):
        async with semaphore:
            start = time.perf_counter()
            errors = []
            profile = {}
            judge_result = None

            try:
                agent = ProfileAgent(use_mock_llm=not has_api)
                result = await agent.extract_and_merge(
                    profile_dict={}, messages=case["messages"],
                )
                profile = result.get("profile", {})
            except Exception as e:
                errors.append(str(e))

            # 构造评估: 把画像格式化为文本让 profile judge 评估
            profile_text = _format_profile_for_judge(profile, case["check_dims"])
            user_msgs = " | ".join(
                m.get("content", "")[:80]
                for m in case["messages"] if m.get("role") == "user"
            )
            if profile_text and not errors:
                judge_result = await judge_profile_quality(
                    user_msgs, case["difficulty"], profile_text,
                )

            score = float(judge_result["total"]) if judge_result else 0.0
            elapsed = (time.perf_counter() - start) * 1000
            details = {"judge_used": judge_result is not None}
            if judge_result:
                details.update(_j_details(judge_result, elapsed))

            return CaseResult(
                case_id=case["id"], difficulty=case["difficulty"],
                category="p2", message=case["messages"][0]["content"][:60],
                desc=case["desc"], score=score, details=details,
                errors=errors, raw_output=profile_text[:300],
            )

    results = await asyncio.gather(*[run_one(c) for c in P2_CASES])
    return list(results)


def _format_profile_for_judge(profile: dict, check_dims: list[str]) -> str:
    labels = {
        "knowledge_base": "知识基础", "cognitive_style": "学习风格",
        "learning_goal": "学习目标", "weak_points": "薄弱环节",
        "learning_pace": "学习节奏", "interest_direction": "兴趣方向",
    }
    lines = ["【提取的画像维度】"]
    for dim in check_dims:
        val = profile.get(dim)
        label = labels.get(dim, dim)
        if val is None or val == [] or val == "":
            lines.append(f"  {label}: (未提取到)")
        elif isinstance(val, list):
            items = [f"{e.get('content', str(e))}" if isinstance(e, dict) else str(e)
                     for e in val[:3]]
            lines.append(f"  {label}: {'; '.join(items)}")
        elif isinstance(val, (int, float)):
            lines.append(f"  {label}: {val}/100")
        else:
            lines.append(f"  {label}: {val}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# P3 ExerciseAgent Runner
# ═══════════════════════════════════════════════════════════════════════════

async def run_p3_tests(semaphore: asyncio.Semaphore) -> list[CaseResult]:
    has_api = bool(os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
                   or os.getenv("DASHSCOPE_API_KEY_FLASH"))

    async def run_one(case):
        async with semaphore:
            start = time.perf_counter()
            errors = []
            output_text = ""
            judge_result = None

            if case["type"] == "exercise_gen":
                try:
                    from app.agents.exercise_agent import ExerciseAgent
                    agent = ExerciseAgent(use_mock_llm=not has_api)
                    state = await agent.run({
                        "topic": case["params"]["topic"],
                        "count": case["params"]["count"],
                        "difficulty": case["params"]["difficulty"],
                        "purpose": case["params"]["purpose"],
                        "student_profile": {},
                    })
                    questions = state.get("questions", [])
                    output_text = _format_exercises_for_judge(
                        case["params"]["topic"], case["params"]["difficulty"],
                        case["params"]["count"], questions,
                    )
                except Exception as e:
                    errors.append(str(e))

            elif case["type"] == "error_analysis":
                try:
                    from app.agents.tutor_agent import TutorAgent
                    agent = TutorAgent(use_mock_llm=not has_api)
                    analysis_prompt = (
                        f"题目：{case['question']}\n\n"
                        f"学生答案：{case['student_answer']}\n\n"
                        f"请分析学生的错误原因，指出具体哪里理解有误，并给出正确解法和学习建议。"
                    )
                    state = await agent.run({
                        "messages": [{"role": "user", "content": analysis_prompt}],
                        "user_id": 1, "student_profile": {}, "course_id": "AI101",
                    })
                    output_text = state.get("response", "")
                except Exception as e:
                    errors.append(str(e))

            if output_text and not errors:
                if case["type"] == "exercise_gen":
                    params = case["params"]
                    judge_question = (
                        f"主题={params['topic']}, 难度={params['difficulty']}, "
                        f"数量={params['count']}, 用途={params['purpose']}"
                    )
                    judge_result = await judge_exercise_quality(
                        judge_question, case["difficulty"], output_text,
                    )
                else:
                    judge_question = case.get("question", case["desc"])
                    judge_result = await judge_quality(
                        judge_question, case["difficulty"], output_text,
                    )

            score = float(judge_result["total"]) if judge_result else 0.0
            elapsed = (time.perf_counter() - start) * 1000
            details = {"judge_used": judge_result is not None}
            if judge_result:
                details.update(_j_details(judge_result, elapsed))

            return CaseResult(
                case_id=case["id"], difficulty=case["difficulty"],
                category="p3", message=case.get("question", case["desc"])[:60],
                desc=case["desc"], score=score, details=details,
                errors=errors, raw_output=output_text[:400],
            )

    results = await asyncio.gather(*[run_one(c) for c in P3_CASES])
    return list(results)


def _format_exercises_for_judge(topic: str, difficulty: str, count: int,
                                questions: list) -> str:
    lines = [
        f"出题要求: 主题={topic}, 难度={difficulty}, 数量={count}",
        f"实际生成 {len(questions)} 道题:",
    ]
    for i, q in enumerate(questions, 1):
        if isinstance(q, dict):
            q_type = q.get("type", q.get("question_type", "?"))
            q_text = q.get("question", q.get("content", str(q)))[:200]
            lines.append(f"  [{i}] 类型={q_type} | {q_text}")
        else:
            lines.append(f"  [{i}] {str(q)[:200]}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Report
# ═══════════════════════════════════════════════════════════════════════════

DIFFICULTY_LABELS = {1: "★☆☆", 2: "★★☆", 3: "★★★"}


def print_report(p2_results, p3_results):
    all_results = p2_results + p3_results

    print()
    print("=" * 95)
    print("  P2+P3 联合测试：24 例 ProfileAgent + ExerciseAgent — 结果报告")
    print("=" * 95)

    for r in all_results:
        diff_label = DIFFICULTY_LABELS.get(r.difficulty, "???")
        cat_label = {"p2": "P2", "p3": "P3"}[r.category]
        status = "[PASS]" if r.score >= 70 else "[FAIL]"
        msg_short = r.message[:55] + "..." if len(r.message) > 55 else r.message

        print(f"\n  ┌─ [{r.case_id:2d}] {cat_label} {diff_label} {status} "
              f"({r.score:.1f}/100)")
        print(f"  │ 输入: {msg_short}")
        print(f"  │ 说明: {r.desc}")

        if r.errors:
            for e in r.errors:
                print(f"  │ ❌ 错误: {e}")

        print(f"  │ 评分明细: {r.details}")

        if r.raw_output:
            preview = r.raw_output[:250].replace("\n", "\\n")
            print(f"  │ 输出: {preview}...")

    print()
    print("=" * 95)
    print("  汇总统计")
    print("=" * 95)

    def stats(results, label):
        if not results:
            print(f"  {label}: (无结果)")
            return 0.0
        avg = sum(r.score for r in results) / len(results)
        passed = sum(1 for r in results if r.score >= 70)
        failed = len(results) - passed
        status = "[PASS]" if avg >= 70 else "[FAIL]"
        print(f"  {label:30s} 平均分: {avg:5.1f}  {status}  "
              f"(通过: {passed}/{len(results)}, 失败: {failed}/{len(results)})")
        return avg

    p2_avg = stats(p2_results, "P2 ProfileAgent (10 例)")
    p3_avg = stats(p3_results, "P3 ExerciseAgent (14 例)")

    weighted_total = p2_avg * 0.45 + p3_avg * 0.55
    grand_pass = weighted_total > 85 and p2_avg >= 70 and p3_avg >= 70

    print(f"  {'─' * 55}")
    print(f"  加权总分 (P2×0.45 + P3×0.55): {weighted_total:.1f}")
    print(f"  判定: {'[PASS] ✓' if grand_pass else '[FAIL] ✗'}")

    print()
    print("  按难度分层:")
    for diff in [1, 2, 3]:
        diff_results = [r for r in all_results if r.difficulty == diff]
        if diff_results:
            avg = sum(r.score for r in diff_results) / len(diff_results)
            passed = sum(1 for r in diff_results if r.score >= 70)
            label = DIFFICULTY_LABELS[diff]
            print(f"    {label} ({len(diff_results)}例)  平均: {avg:.1f}  "
                  f"通过: {passed}/{len(diff_results)}")

    print()
    print("=" * 95)
    return grand_pass


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    print("=" * 95)
    print("  P2+P3 联合测试：24 例 ProfileAgent + ExerciseAgent")
    print("=" * 95)

    print("\n  [1/2] P2 (10 例) + P3 (14 例) 并行跑 [LLM-as-Judge, 并发=12]...\n")
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    p2_results, p3_results = await asyncio.gather(
        run_p2_tests(semaphore), run_p3_tests(semaphore),
    )
    print("\n  --- P2 ProfileAgent 画像提取 ---")
    for r in p2_results:
        marker = "✓" if r.score >= 70 else "✗"
        j = r.details
        judge_info = ""
        if j.get("judge_used"):
            judge_info = (f"A{j.get('judge_accuracy',0)} D{j.get('judge_depth',0)} "
                         f"H{j.get('judge_helpfulness',0)} S{j.get('judge_structure',0)} "
                         f"F{j.get('judge_domain_fit',0)}")
        else:
            judge_info = "(judge 不可用)"
        print(f"    [{r.case_id:2d}] {marker} {r.score:.1f}/100  "
              f"{judge_info}  {r.desc[:40]}")

    print("\n  --- P3 ExerciseAgent 出题+错因分析 ---")
    for r in p3_results:
        marker = "✓" if r.score >= 70 else "✗"
        j = r.details
        judge_info = ""
        if j.get("judge_used"):
            judge_info = (f"A{j.get('judge_accuracy',0)} D{j.get('judge_depth',0)} "
                         f"H{j.get('judge_helpfulness',0)} S{j.get('judge_structure',0)} "
                         f"F{j.get('judge_domain_fit',0)}")
        else:
            judge_info = "(judge 不可用)"
        print(f"    [{r.case_id:2d}] {marker} {r.score:.1f}/100  "
              f"{judge_info}  {r.desc[:40]}")

    grand_pass = print_report(p2_results, p3_results)
    return 0 if grand_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
