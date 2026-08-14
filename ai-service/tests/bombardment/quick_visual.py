"""可视化快速串行测试 — 逐个场景发送，避免服务过载"""
import json, os, sys, time
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tests.bombardment.scenarios_visual import SCENARIOS
from tests.bombardment.run_visual import _extract_sse_full, _deterministic_check

sys.stdout.reconfigure(encoding="utf-8", errors="replace") if hasattr(sys.stdout, "reconfigure") else None

for i, s in enumerate(SCENARIOS):
    print(f"\n{'='*60}")
    print(f"[{i+1}/10] {s['id']}: {s['description']}")
    print(f"  期望触发: {s.get('expected_trigger')}")

    body = s["request"]["body"]
    t0 = time.time()
    try:
        r = requests.post(s["request"]["url"], json=body, timeout=180)
        elapsed = time.time() - t0
        if r.status_code == 200:
            parsed = _extract_sse_full(r.text)
            text = parsed["text"]
            blocks = parsed["blocks"]
            det = _deterministic_check(blocks)

            triggered = "VIS" if blocks else "TXT"
            sources = set(b.get("source", "?") for b in blocks)
            print(f"  耗时: {elapsed:.1f}s | 状态: 200 | 触发: {triggered} | 来源: {sources}")

            if blocks:
                for b in blocks:
                    src = b.get("source", "?")
                    print(f"  Block: type={b['type']}, title={b['title']}, code_len={len(b['code'])}, source={src}")
                for c in det["checks"]:
                    status = "PASS" if c["valid"] else f"FAIL: {c['error']}"
                    print(f"  确定性校验 [{c['type']}]: {status}")

            preview = text[:200].replace("\n", " ")
            print(f"  文本预览: {preview}...")
        else:
            elapsed = time.time() - t0
            print(f"  耗时: {elapsed:.1f}s | HTTP {r.status_code} | {r.text[:200]}")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  耗时: {elapsed:.1f}s | EXCEPTION: {e}")

    # 间隔 5 秒让服务喘息
    if i < len(SCENARIOS) - 1:
        print("  (waiting 5s...)")
        time.sleep(5)

print(f"\n{'='*60}")
print("Done.")
