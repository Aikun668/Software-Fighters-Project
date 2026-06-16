"""捕获 plan pipeline 中所有 LLM 中间产物 — 直接调用 Agent。

展示：
  1) GoalAgent     → 目标提取结果
  2) DecomposeAgent → 知识点分解结果
  3) ScheduleAgent  → 排程结果 (steps + milestones)
"""
import asyncio
import json
import sys
import os

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.agents.goal_agent import GoalAgent
from app.agents.decompose_agent import DecomposeAgent
from app.agents.schedule_agent import ScheduleAgent


async def main():
    topic = "学习机器学习基础，从数学到神经网络入门"
    student_profile = {
        "weak_points": ["微积分"],
        "strong_points": ["Python编程"],
        "skill_levels": {"math": 0.6, "python": 0.8, "ml": 0.2}
    }

    # ── 1. GoalAgent ──
    print("=" * 70)
    print("  1. GoalAgent — 目标提取")
    print("=" * 70)
    goal_agent = GoalAgent(use_mock_llm=False)
    goal_state = await goal_agent.run({
        "input": topic,
        "context": "",
        "student_profile": student_profile,
    })
    goal = {
        "goal_title": goal_state.get("goal_title", topic),
        "target_topic": goal_state.get("target_topic", topic),
        "target_level": goal_state.get("target_level", "understand"),
        "deadline": goal_state.get("deadline", ""),
        "motivation": goal_state.get("motivation", ""),
        "constraints": goal_state.get("constraints", []),
    }
    print(json.dumps(goal, ensure_ascii=False, indent=2))
    print(f"\n  [原始 state keys]: {list(goal_state.keys())}")
    if "response" in goal_state:
        print(f"  [LLM raw response preview]: {str(goal_state.get('response', ''))[:200]}")

    # ── 2. DecomposeAgent ──
    print("\n" + "=" * 70)
    print("  2. DecomposeAgent — 知识点分解")
    print("=" * 70)
    effective_topic = goal.get("target_topic") or topic
    decompose_agent = DecomposeAgent(use_mock_llm=False)
    decompose_state = await decompose_agent.run({
        "topic": effective_topic,
        "context": topic,
        "student_profile": student_profile,
    })
    decomposition = {
        "macro_topics": decompose_state.get("macro_topics", []),
        "micro_skills": decompose_state.get("micro_skills", []),
        "prerequisites": decompose_state.get("prerequisites", []),
    }
    print(f"  macro_topics: {len(decomposition['macro_topics'])} 个")
    for mt in decomposition["macro_topics"]:
        print(f"    - {mt.get('name', '?')} (bloom={mt.get('bloom_level', '?')})")
    print(f"  micro_skills: {len(decomposition['micro_skills'])} 个")
    for ms in decomposition["micro_skills"][:8]:
        print(f"    - {ms.get('name', '?')} (parent={ms.get('parent', '?')})")
    if len(decomposition["micro_skills"]) > 8:
        print(f"    ... and {len(decomposition['micro_skills']) - 8} more")
    print(f"  prerequisites: {len(decomposition['prerequisites'])} 个")
    for pr in decomposition["prerequisites"]:
        print(f"    - {pr.get('name', '?')} ({pr.get('relation', '?')})")
    print(f"\n  [原始 state keys]: {list(decompose_state.keys())}")

    # ── 3. ScheduleAgent ──
    print("\n" + "=" * 70)
    print("  3. ScheduleAgent — 排程")
    print("=" * 70)
    schedule_agent = ScheduleAgent(use_mock_llm=False)
    schedule_state = await schedule_agent.run({
        "goal": goal,
        "decomposition": decomposition,
        "student_profile": student_profile,
        "existing_plan": {},
    })
    steps = schedule_state.get("steps", [])
    raw_milestones = schedule_state.get("milestones", [])
    print(f"  plan_title: {schedule_state.get('plan_title', 'N/A')}")
    print(f"  estimated_days: {schedule_state.get('estimated_days', 'N/A')}")
    print(f"  daily_capacity: {schedule_state.get('daily_capacity', 'N/A')}")
    print(f"  steps: {len(steps)} 步")
    for s in steps[:5]:
        print(f"    Step {s.get('step_order', s.get('day', '?'))}: {s.get('topic', '?')} ({s.get('type', '?')})")
    if len(steps) > 5:
        print(f"    ... and {len(steps) - 5} more")
    print(f"  milestones (raw, {len(raw_milestones)}):")
    for i, m in enumerate(raw_milestones):
        print(f"    [{i}] type={type(m).__name__}: {m}")
    print(f"\n  [原始 state keys]: {list(schedule_state.keys())}")
    summary = schedule_state.get("response", "")
    if summary:
        print(f"  [summary]: {summary[:300]}")

    print("\n" + "=" * 70)
    print("  管线完成 — 所有中间产物已展示")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
