"""打印 P5 Plan 8 用例 —— 输入 + 完整流水线输出（不跑 judge）

用法:
    cd ai-service && PYTHONPATH=. python tests/print_p5_plans.py
"""
import asyncio, json, os, sys, time

from dotenv import load_dotenv
load_dotenv()

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import logging
logging.getLogger("app.utils.content_guard").setLevel(logging.ERROR)
logging.getLogger("app.utils.security_logger").setLevel(logging.ERROR)

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

DIFF = {1: "★☆☆", 2: "★★☆", 3: "★★★"}


def _print_json(title: str, data: dict | list, indent: int = 2):
    print(title)
    print(json.dumps(data, ensure_ascii=False, indent=indent))
    print()


async def run_one(case: dict):
    """Run full pipeline for one case, print everything."""
    has_api = bool(os.getenv("MINIMAX_API_KEY") or os.getenv("OPENAI_API_KEY")
                   or os.getenv("DASHSCOPE_API_KEY") or os.getenv("DASHSCOPE_API_KEY_FLASH"))

    from app.agents.goal_agent import GoalAgent
    from app.agents.decompose_agent import DecomposeAgent
    from app.agents.schedule_agent import ScheduleAgent

    t0 = time.perf_counter()

    # ── Goal ──
    gs = None
    try:
        ga = GoalAgent(use_mock_llm=not has_api)
        gs = await ga.run({"input": case["input"], "context": "", "student_profile": {}})
    except Exception as e:
        gs = {"error": f"GoalAgent crashed: {e}"}

    # ── Decompose ──
    ds = None
    try:
        da = DecomposeAgent(use_mock_llm=not has_api)
        ds = await da.run({"topic": (gs or {}).get("target_topic", case["input"]),
                            "context": case["input"], "student_profile": {}})
    except Exception as e:
        ds = {"error": f"DecomposeAgent crashed: {e}"}

    # ── Schedule ──
    ss = None
    try:
        sa = ScheduleAgent(use_mock_llm=not has_api)
        ss = await sa.run({"goal": {
            "goal_title": (gs or {}).get("goal_title", ""),
            "target_topic": (gs or {}).get("target_topic", ""),
            "target_level": (gs or {}).get("target_level", ""),
            "deadline": (gs or {}).get("deadline", ""),
            "motivation": (gs or {}).get("motivation", ""),
            "constraints": (gs or {}).get("constraints", []),
        }, "decomposition": {
            "macro_topics": (ds or {}).get("macro_topics", []),
            "micro_skills": (ds or {}).get("micro_skills", []),
            "prerequisites": (ds or {}).get("prerequisites", []),
            "summary": (ds or {}).get("summary", ""),
        }, "student_profile": {}, "existing_plan": {}})
    except Exception as e:
        ss = {"error": f"ScheduleAgent crashed: {e}"}

    elapsed = time.perf_counter() - t0

    # ── Print ──
    d = DIFF.get(case["diff"], "???")
    print("=" * 80)
    print(f"  Case #{case['id']}  {d}  {case['desc']}")
    print("=" * 80)
    print(f"\n  【用户输入】\n  {case['input']}\n")
    print(f"  耗时: {elapsed:.1f}s\n")

    _print_json("  ── GoalAgent 输出 ──", gs or {})
    _print_json("  ── DecomposeAgent 输出 ──", ds or {})
    _print_json("  ── ScheduleAgent 输出 ──", ss or {})

    return elapsed


async def main():
    import traceback

    output_path = os.path.join(os.path.dirname(__file__), "_p5_full_output.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("  P5 Plan 流水线：8 用例完整输出\n")
        f.write("=" * 80 + "\n\n")

    total = 0.0
    for case in CASES:
        try:
            elapsed = await run_one(case)
            total += elapsed
        except Exception:
            print(f"\n  [ERROR] Case #{case['id']} crashed!", file=sys.stderr)
            traceback.print_exc()
            # 不阻断后续用例
            continue

    print(f"\n{'=' * 80}")
    print(f"  全部 {len(CASES)} 用例完成，总耗时 {total:.1f}s")
    print(f"  输出文件: {output_path}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
