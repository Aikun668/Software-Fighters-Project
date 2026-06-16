"""展示测试用例 + 管线完整产物。

1) 输入：测试用例列表（含输入参数）
2) 输出：create-from-path 完整 JSON（steps, milestones, goal, decomposition, schedule）
"""
import asyncio
import json
import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.agents.goal_agent import GoalAgent
from app.agents.decompose_agent import DecomposeAgent
from app.agents.schedule_agent import ScheduleAgent


TEST_CASES = [
    # ──── 基础场景 ────
    {
        "topic": "学习机器学习基础，从数学到神经网络入门",
        "student_profile": {
            "weak_points": ["微积分"],
            "strong_points": ["Python编程"],
            "skill_levels": {"math": 0.6, "python": 0.8, "ml": 0.2},
        },
    },
    {
        "topic": "掌握 Python 面向对象编程与设计模式",
        "student_profile": {
            "weak_points": [],
            "strong_points": ["Python基础"],
            "skill_levels": {"python": 0.7, "oop": 0.3},
        },
    },
    {
        "topic": "学习数据结构与算法，重点图论与动态规划",
        "student_profile": {
            "weak_points": ["递归", "复杂度分析"],
            "strong_points": ["数组操作"],
            "skill_levels": {"dsa": 0.4, "math": 0.5},
        },
    },
    # ──── 边界场景 ────
    {
        "topic": "深度学习计算机视觉",
        "student_profile": {
            "weak_points": [],
            "strong_points": [],
            "skill_levels": {},
        },
    },
    {
        "topic": "入门 SQL 数据库查询与优化",
        "student_profile": {
            "weak_points": ["数据库理论"],
            "strong_points": ["逻辑思维"],
            "skill_levels": {"sql": 0.1},
        },
    },
]


async def run_one(idx: int, tc: dict):
    topic = tc["topic"]
    profile = tc["student_profile"]

    goal_agent = GoalAgent(use_mock_llm=False)
    decompose_agent = DecomposeAgent(use_mock_llm=False)
    schedule_agent = ScheduleAgent(use_mock_llm=False)

    # Step 1
    goal_state = await goal_agent.run({"input": topic, "context": "", "student_profile": profile})
    goal = {
        "goal_title": goal_state.get("goal_title", topic),
        "target_topic": goal_state.get("target_topic", topic),
        "target_level": goal_state.get("target_level", "understand"),
        "deadline": goal_state.get("deadline", ""),
        "motivation": goal_state.get("motivation", ""),
        "constraints": goal_state.get("constraints", []),
    }

    # Step 2
    decompose_state = await decompose_agent.run({
        "topic": goal.get("target_topic") or topic,
        "context": topic,
        "student_profile": profile,
    })
    decomposition = {
        "macro_topics": decompose_state.get("macro_topics", []),
        "micro_skills": decompose_state.get("micro_skills", []),
        "prerequisites": decompose_state.get("prerequisites", []),
    }

    # Step 3
    schedule_state = await schedule_agent.run({
        "goal": goal, "decomposition": decomposition,
        "student_profile": profile, "existing_plan": {},
    })
    steps = schedule_state.get("steps", [])
    milestones = schedule_state.get("milestones", [])

    result = {
        "idx": idx,
        "topic": topic,
        "goal": goal,
        "decomposition": {
            "macro_topics_count": len(decomposition["macro_topics"]),
            "macro_topics": [m.get("name", "?") if isinstance(m, dict) else str(m) for m in decomposition["macro_topics"]],
            "micro_skills_count": len(decomposition["micro_skills"]),
            "micro_skills": [m.get("name", "?") if isinstance(m, dict) else str(m) for m in decomposition["micro_skills"]],
            "prerequisites_count": len(decomposition["prerequisites"]),
            "prerequisites": [p.get("name", "?") if isinstance(p, dict) else str(p) for p in decomposition["prerequisites"]],
        },
        "schedule": {
            "plan_title": schedule_state.get("plan_title", ""),
            "estimated_days": schedule_state.get("estimated_days", 0),
            "daily_capacity": schedule_state.get("daily_capacity", 0),
            "total_steps": len(steps),
            "steps": [{
                "step_order": s.get("step_order", s.get("day", "?")),
                "topic": s.get("topic", "?"),
                "type": s.get("type", "?"),
                "bloom_level": s.get("bloom_level", ""),
            } for s in steps],
            "milestones_raw": milestones,
            "summary": schedule_state.get("response", ""),
        },
    }
    return result


async def main():
    results = []
    for i, tc in enumerate(TEST_CASES, start=1):
        print(f"Running case {i}/{len(TEST_CASES)}: {tc['topic'][:50]}...", file=sys.stderr)
        r = await run_one(i, tc)
        results.append(r)

    # 输出漂亮 JSON
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
