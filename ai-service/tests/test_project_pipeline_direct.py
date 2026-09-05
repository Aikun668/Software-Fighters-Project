"""ProjectAgent Path A — 直接调 Agent + DOCX 导出 端到端验证"""
import asyncio, json, os, sys, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

DESKTOP = Path.home() / "Desktop"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from app.agents.project_agent import ProjectAgent
from app.services.llm_service import AgentModelProfile, ModelConfig

# 使用 MiniMax Token Plan
_MM_KEY = os.getenv("MINIMAX_API_KEY", "")
_MM_BASE = os.getenv("MINIMAX_BASE_URL", "")
PROFILE = AgentModelProfile(
    default=ModelConfig(model="MiniMax-M3", temperature=0.7, max_tokens=8192,
                        api_key=_MM_KEY, base_url=_MM_BASE),
)


async def run_full_pipeline(topic: str, student_profile: dict, case_name: str):
    print(f"\n{'='*60}")
    print(f"Case: {case_name} — {topic}")
    print(f"{'='*60}")

    agent = ProjectAgent(use_mock_llm=False, model_profile=PROFILE)

    # Step 1: Run agent
    t0 = time.time()
    state = {
        "topic": topic,
        "prerequisites": f"knowledge_base={student_profile.get('knowledge_base', 0)}",
        "student_profile": student_profile,
    }
    result = await agent.run(state)
    elapsed = time.time() - t0
    print(f"Agent done in {elapsed:.1f}s")

    blocks = result.get("blocks", [])
    response = result.get("response", "")

    if not blocks:
        print("FAIL: no blocks!")
        return False

    b = blocks[0]
    c = b.get("content", {})
    ms = c.get("milestones", [])
    print(f"Title: {c.get('title', '?')[:80]}")
    print(f"Milestones: {len(ms)}")
    all_ok = True
    for m in ms:
        code_ok = len(m.get("code", "")) > 20 and "TODO" not in m.get("code", "")[:50]
        expl_ok = len(m.get("explanation", "")) > 20
        outp_ok = len(m.get("expected_output", "")) > 10
        status = "OK" if (code_ok and expl_ok and outp_ok) else "MISSING"
        if status != "OK":
            all_ok = False
        print(f"  S{m.get('step')}: code={len(m.get('code',''))}c "
              f"expl={len(m.get('explanation',''))}c "
              f"outp={len(m.get('expected_output',''))}c [{status}]")

    # Save JSON
    json_path = DESKTOP / f"project_path_a_{case_name}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"topic": topic, "blocks": blocks, "response": response},
                  f, ensure_ascii=False, indent=2)
    print(f"JSON: {json_path}")

    # Step 2: DOCX export
    print("\n--- DOCX Export ---")
    from app.utils.docx_exporter import export_to_docx
    docx_path = str(DESKTOP / f"project_path_a_{case_name}.docx")
    try:
        result_path = export_to_docx(blocks, docx_path, c.get("title", topic), "guide")
        size = os.path.getsize(result_path)
        print(f"DOCX: {result_path} ({size} bytes)")
    except Exception as e:
        print(f"DOCX export failed: {e}")
        import traceback
        traceback.print_exc()
        all_ok = False

    print(f"Result: {'PASS' if all_ok else 'FAIL'}")
    return all_ok


async def main():
    print("ProjectAgent Path A — Direct Pipeline Test")
    print(f"Desktop: {DESKTOP}")

    results = await asyncio.gather(
        run_full_pipeline(
            topic="Python文件读写与上下文管理器",
            student_profile={"knowledge_base": 40, "weak_points": ["文件操作", "异常处理"]},
            case_name="file_io",
        ),
        run_full_pipeline(
            topic="梯度下降优化算法",
            student_profile={"knowledge_base": 60, "weak_points": ["微积分", "矩阵运算"]},
            case_name="gradient_descent",
        ),
    )

    print(f"\n{'='*60}")
    print(f"OVERALL: {'ALL PASS' if all(results) else 'SOME FAILED'}")
    print(f"Files on desktop:")
    for f in sorted(DESKTOP.glob("project_path_a_*")):
        print(f"  {f.name} ({f.stat().st_size} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
