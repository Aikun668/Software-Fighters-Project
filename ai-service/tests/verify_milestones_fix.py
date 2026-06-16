"""验证 milestones 标准化修复是否在所有端点生效。"""
import json
import sys
import httpx

BASE = "http://localhost:8100/internal"


def main():
    client = httpx.Client(trust_env=False, timeout=120)
    passed = 0
    failed = 0

    # ── 1. create-from-path ──
    print("=" * 60)
    print("1) POST /plans/create-from-path")
    r = client.post(f"{BASE}/plans/create-from-path", json={
        "user_id": 1, "course_id": "ai_intro",
        "topic": "Learn ML basics with neural networks",
        "student_profile": {}
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:300]}"
    data = r.json()
    assert data.get("success"), f"create-from-path failed: {data}"
    plan_data = data["data"]
    steps = plan_data["steps"]
    milestones = plan_data["milestones"]
    total_steps = plan_data["total_steps"]
    plan = {
        "id": 1, "user_id": 1, "status": "active",
        "total_steps": total_steps, "completed_steps": 0,
        "start_date": "2026-06-15", "last_activity_at": "2026-06-15T10:00:00Z",
        "milestones": milestones,
    }

    # Check milestones are dicts
    assert isinstance(milestones, list) and len(milestones) > 0, "milestones empty"
    for m in milestones:
        assert isinstance(m, dict), f"milestone is not dict: {m}"
        assert "milestone_id" in m, f"missing milestone_id: {m}"
        assert "after_step" in m, f"missing after_step: {m}"
        assert "description" in m, f"missing description: {m}"
    print(f"   [PASS] {len(steps)} steps, {len(milestones)} milestones (all dicts)")
    print(f"   Milestones: {json.dumps(milestones, ensure_ascii=False)[:300]}")
    passed += 1

    # ── 2. plan status ──
    print("=" * 60)
    print("2) POST /plans/{plan_id}/status")
    r = client.post(f"{BASE}/plans/1/status", json={
        "plan": plan, "steps": steps
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:300]}"
    status_data = r.json()
    assert status_data.get("success"), f"plan status failed: {status_data}"
    print(f"   [PASS] status=200, has next_milestone: {status_data['data'].get('next_milestone') is not None}")
    passed += 1

    # ── 3. today ──
    print("=" * 60)
    print("3) POST /plans/{plan_id}/today")
    r = client.post(f"{BASE}/plans/1/today", json={
        "plan": plan, "steps": steps, "start_date": "2026-06-15",
        "masteries": {}
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:300]}"
    today_data = r.json()
    assert today_data.get("success"), f"today failed: {today_data}"
    today_steps = today_data["data"].get("today_steps", [])
    print(f"   [PASS] status=200, today_steps={len(today_steps)}, next_milestone={'yes' if today_data['data'].get('next_milestone') else 'no'}")
    passed += 1

    # ── 4. progress ──
    print("=" * 60)
    print("4) POST /plans/{plan_id}/progress")
    # Mark first step complete
    r = client.post(f"{BASE}/plans/1/progress", json={
        "user_id": 1, "step_id": 0, "step_order": 1,
        "status": "completed", "score": 0.85,
        "activity_type": "exercise", "duration_minutes": 30,
        "plan": {**plan, "completed_steps": 1}, "steps": steps,
        "masteries": {}
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:300]}"
    prog_data = r.json()
    assert prog_data.get("success"), f"progress failed: {prog_data}"
    print(f"   [PASS] status=200, mastery_updates={len(prog_data['data'].get('mastery_updates', []))}")
    passed += 1

    # ── 5. node-status-change ──
    print("=" * 60)
    print("5) POST /plans/{plan_id}/node-status-change")
    # Grab a knowledge_node_id from steps
    node_ids = [s.get("knowledge_node_id") for s in steps if s.get("knowledge_node_id") and s["knowledge_node_id"] != "unknown"]
    test_node = node_ids[0] if node_ids else "ml_basics"
    r = client.post(f"{BASE}/plans/1/node-status-change", json={
        "node_id": test_node,
        "old_status": "learning", "new_status": "mastered",
        "plan": {**plan, "completed_steps": 2}, "steps": steps,
        "masteries": {test_node: 0.7}
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:300]}"
    node_data = r.json()
    assert node_data.get("success"), f"node-status-change failed: {node_data}"
    print(f"   [PASS] status=200, actions={len(node_data['data'].get('actions', []))}, next_milestone={'yes' if node_data['data'].get('next_milestone') else 'no'}")
    passed += 1

    # ── 6. plan status with all updated data ──
    print("=" * 60)
    print("6) POST /plans/{plan_id}/status (final check)")
    updated_steps = prog_data["data"].get("updated_steps", steps)
    r = client.post(f"{BASE}/plans/1/status", json={
        "plan": {**plan, "completed_steps": 1, "last_activity_at": "2026-06-15T12:00:00Z"},
        "steps": updated_steps
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:300]}"
    print(f"   [PASS] status=200, soft_landing={r.json().get('data',{}).get('soft_landing')}")
    passed += 1

    # ── Summary ──
    print("=" * 60)
    print(f"\nAll {passed}/{passed + failed} tests passed!")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
