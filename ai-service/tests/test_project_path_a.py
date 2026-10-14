"""ProjectAgent Path A 端到端测试 — SSE 生成 → 验证 milestone 包含 code

两个并行用例：
  1. 初学者 + Python列表操作 → 3-4个里程碑，每个含代码
  2. 进阶者 + 神经网络反向传播 → 4-5个里程碑，每个含代码

用法: python tests/test_project_path_a.py
"""

import asyncio
import json
import os
import sys
import tempfile
import urllib.request
import urllib.error
from pathlib import Path

API_BASE = "http://127.0.0.1:8001/internal"
# 输出目录默认落在系统临时目录，避免污染桌面。
# 需要留存结果时设环境变量 PROJECT_PATH_A_OUT 指向目标目录即可。
TEST_OUT_DIR = (
    Path(os.environ.get("PROJECT_PATH_A_OUT") or tempfile.gettempdir())
    / "project_agent_path_a_test"
)

TEST_CASES = [
    {
        "name": "case1_python_lists",
        "topic": "Python列表操作与列表推导式",
        "user_id": 1,
        "resource_type": "project",
        "student_profile": {
            "knowledge_base": 35,
            "cognitive_style": "visual",
            "learning_goal": "掌握Python基础数据结构",
            "weak_points": ["循环", "条件判断"],
            "learning_pace": "slow",
            "interest_direction": "数据分析",
        },
    },
    {
        "name": "case2_backprop",
        "topic": "神经网络反向传播算法",
        "user_id": 1,
        "resource_type": "project",
        "student_profile": {
            "knowledge_base": 65,
            "cognitive_style": "logical",
            "learning_goal": "深入理解深度学习训练机制",
            "weak_points": ["链式法则", "矩阵求导"],
            "learning_pace": "medium",
            "interest_direction": "深度学习框架",
        },
    },
]


def fetch_sse(topic: str, student_profile: dict, resource_type: str) -> list[dict]:
    """通过 urllib 调用 SSE 端点，收集所有事件。"""
    url = f"{API_BASE}/resources/generate"
    body = json.dumps({
        "topic": topic,
        "user_id": 1,
        "student_profile": student_profile,
        "resource_type": resource_type,
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )

    events: list[dict] = []
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            buffer = ""
            for chunk in iter(lambda: resp.read(4096), b""):
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                buffer += text
                while "\n\n" in buffer:
                    line, buffer = buffer.split("\n\n", 1)
                    for part in line.split("\n"):
                        part = part.strip()
                        if part.startswith("data: "):
                            data_str = part[6:]
                            if data_str == ": heartbeat":
                                continue
                            try:
                                event = json.loads(data_str)
                                events.append(event)
                            except json.JSONDecodeError:
                                pass
    except urllib.error.URLError as e:
        print(f"  [ERROR] Connection failed: {e}")
        return []

    return events


def extract_content_blocks(events: list[dict]) -> dict | None:
    """从 done 事件中提取 content_blocks（嵌套在 data 字段下）。"""
    for event in reversed(events):
        if event.get("type") == "done":
            data = event.get("data", {})
            blocks = data.get("content_blocks", [])
            response = data.get("response", "")
            return {"blocks": blocks, "response": response}
    # 兼容旧格式（数据直接在顶层）
    for event in reversed(events):
        if event.get("type") == "done":
            blocks = event.get("content_blocks", [])
            if blocks:
                return {"blocks": blocks, "response": event.get("response", "")}
    return None


def validate_milestone_code(blocks: list[dict]) -> dict:
    """验证每个里程碑都有 explanation / code / expected_output。"""
    report = {"total_milestones": 0, "with_code": 0, "with_explanation": 0,
              "with_expected_output": 0, "avg_code_chars": 0, "issues": []}

    for block in blocks:
        if block.get("type") != "project":
            continue
        content = block.get("content", {})
        milestones = content.get("milestones", [])
        report["total_milestones"] = len(milestones)

        total_code_len = 0
        for m in milestones:
            code = m.get("code", "")
            explanation = m.get("explanation", "")
            expected_output = m.get("expected_output", "")

            if code and len(code) > 20:
                report["with_code"] += 1
                total_code_len += len(code)
            else:
                report["issues"].append(
                    f"Milestone {m.get('step', '?')} '{m.get('title', '')}': "
                    f"code missing or too short ({len(code)} chars)"
                )

            if explanation:
                report["with_explanation"] += 1
            else:
                report["issues"].append(
                    f"Milestone {m.get('step', '?')}: explanation missing"
                )

            if expected_output:
                report["with_expected_output"] += 1
            else:
                report["issues"].append(
                    f"Milestone {m.get('step', '?')}: expected_output missing"
                )

        if report["with_code"] > 0:
            report["avg_code_chars"] = total_code_len // report["with_code"]

    return report


async def run_one(case: dict) -> dict:
    """运行单个测试用例，在 asyncio executor 中调用同步 HTTP。"""
    name = case["name"]
    topic = case["topic"]
    profile = case["student_profile"]
    resource_type = case["resource_type"]

    print(f"\n{'='*60}")
    print(f"Testing: {name} — {topic}")
    print(f"Profile: knowledge_base={profile.get('knowledge_base')}")
    print(f"{'='*60}")

    loop = asyncio.get_running_loop()
    events = await loop.run_in_executor(
        None, fetch_sse, topic, profile, resource_type
    )

    print(f"  SSE events received: {len(events)}")
    event_types = [e.get("type") for e in events]
    stage_events = [e for e in events if e.get("type") in ("stage_start", "stage_end")]
    for se in stage_events:
        print(f"  [{se['type']}] {se.get('stage', '?')}: {se.get('content', '')[:100]}")

    result = extract_content_blocks(events)
    if not result:
        print("  [FAIL] No done event found!")
        return {"case": name, "status": "FAIL", "reason": "No done event", "blocks": []}

    blocks = result["blocks"]
    response = result["response"]
    print(f"  Response: {response[:150]}")
    print(f"  Blocks count: {len(blocks)}")

    # Validate
    report = validate_milestone_code(blocks)
    print(f"  Milestones: {report['total_milestones']}")
    print(f"  With code: {report['with_code']}/{report['total_milestones']}"
          f" (avg {report['avg_code_chars']} chars)")
    print(f"  With explanation: {report['with_explanation']}/{report['total_milestones']}")
    print(f"  With expected_output: {report['with_expected_output']}/{report['total_milestones']}")

    if report["issues"]:
        for issue in report["issues"]:
            print(f"  [ISSUE] {issue}")

    status = "PASS" if report["with_code"] == report["total_milestones"] and report["total_milestones"] >= 2 else "FAIL"

    # Save to file（目录在此处按需创建，不再在模块导入时创建）
    TEST_OUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = TEST_OUT_DIR / f"{name}_result.json"
    output_data = {
        "topic": topic,
        "student_profile": profile,
        "response": response,
        "blocks": blocks,
        "validation": report,
        "status": status,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"  Saved: {output_path}")

    # Also save a readable markdown version
    md_path = TEST_OUT_DIR / f"{name}_readable.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# {topic} — 项目实战\n\n")
        f.write(f"**Status**: {status}\n\n")
        f.write(f"**Response**: {response}\n\n")
        for block in blocks:
            if block.get("type") == "project":
                c = block.get("content", {})
                f.write(f"## {c.get('title', '')}\n\n")
                f.write(f"- Difficulty: {c.get('difficulty', '')}\n")
                f.write(f"- Tech Stack: {', '.join(c.get('tech_stack', []))}\n")
                f.write(f"- Time Estimate: {c.get('time_estimate', '')}\n\n")
                f.write(f"### Description\n\n{c.get('description', '')}\n\n")
                f.write(f"### Learning Objectives\n\n")
                for obj in c.get("learning_objectives", []):
                    f.write(f"- {obj}\n")
                f.write(f"\n### Milestones\n\n")
                for m in c.get("milestones", []):
                    f.write(f"#### Step {m.get('step', '?')}: {m.get('title', '')}\n\n")
                    f.write(f"**Goal**: {m.get('goal', '')}\n\n")
                    f.write(f"**Deliverable**: {m.get('deliverable', '')}\n\n")
                    f.write(f"**Hint**: {m.get('hint', '')}\n\n")
                    if m.get("explanation"):
                        f.write(f"**Explanation**:\n\n{m['explanation']}\n\n")
                    if m.get("code"):
                        f.write(f"**Code**:\n\n```python\n{m['code']}\n```\n\n")
                    if m.get("expected_output"):
                        f.write(f"**Expected Output**:\n\n```\n{m['expected_output']}\n```\n\n")
                    f.write("---\n\n")
    print(f"  Saved: {md_path}")

    return {"case": name, "status": status, "report": report, "blocks": blocks}


async def main():
    print("=" * 60)
    print("ProjectAgent Path A — E2E Parallel Test")
    print(f"API: {API_BASE}/resources/generate")
    print(f"Output: {TEST_OUT_DIR}")
    print("=" * 60)

    results = await asyncio.gather(
        run_one(TEST_CASES[0]),
        run_one(TEST_CASES[1]),
    )

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    all_pass = True
    for r in results:
        status = r["status"]
        report = r.get("report", {})
        print(f"  {r['case']}: {status} "
              f"(milestones: {report.get('total_milestones', 0)}, "
              f"code: {report.get('with_code', 0)}, "
              f"explanation: {report.get('with_explanation', 0)}, "
              f"expected_output: {report.get('with_expected_output', 0)})")
        if status != "PASS":
            all_pass = False

    print(f"\n  Overall: {'ALL PASS' if all_pass else 'SOME FAILED'}")
    print(f"  Output directory: {TEST_OUT_DIR}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
