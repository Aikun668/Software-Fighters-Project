"""Task 4 Step 3: 真实 SSE 验收 - /internal/inquiry/resolve

构造的追问输入 + 真实 /inquiry/resolve SSE, 解析 done.data 全字段。
"""
import json
import sys
import time
import urllib.request


def post_sse(url: str, body: dict, timeout_s: float = 120.0) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    t0 = time.time()
    resp = urllib.request.urlopen(req, timeout=timeout_s)
    raw = resp.read().decode("utf-8")
    elapsed = time.time() - t0
    return {
        "status": resp.status,
        "content_type": resp.headers.get("Content-Type", ""),
        "elapsed_s": round(elapsed, 2),
        "raw": raw,
    }


def parse_sse(raw: str) -> list[dict]:
    events = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        for line in block.split("\n"):
            if line.startswith("data: "):
                payload = line[len("data: "):]
                try:
                    events.append(json.loads(payload))
                except json.JSONDecodeError:
                    events.append({"_raw": payload})
                break
    return events


def main() -> int:
    url = "http://127.0.0.1:8000/internal/inquiry/resolve"
    body = {
        "user_id": 7,
        "original_message": "想学反向传播",
        "answers": ["先讲直觉再给公式"],
        "questions": [
            {"text": "想要公式推导还是直觉讲解？", "options": []},
        ],
        "suggested_types": ["document", "mindmap"],
        "clarified_topic": "反向传播",
        "student_profile": {"level": "intermediate", "goal": "self_study"},
    }

    print(f"POST {url}")
    print(f"body keys: {list(body.keys())}")
    result = post_sse(url, body, timeout_s=120.0)

    print(f"\nHTTP {result['status']}  content-type={result['content_type']}  elapsed={result['elapsed_s']}s")
    print(f"raw bytes: {len(result['raw'])}")

    events = parse_sse(result["raw"])
    print(f"events total: {len(events)}")
    types_count: dict[str, int] = {}
    for e in events:
        t = e.get("type", "<unknown>")
        types_count[t] = types_count.get(t, 0) + 1
    print(f"event types: {types_count}")

    done_events = [e for e in events if e.get("type") == "done"]
    print(f"\ndone events: {len(done_events)}")
    if not done_events:
        print("NO DONE EVENT - FAIL")
        return 1
    if len(done_events) > 1:
        print(f"WARNING: multiple done events: {len(done_events)}")

    data = done_events[0].get("data", {})
    print(f"\ndone.data keys: {list(data.keys())}")

    required = ["content_blocks", "questions", "response", "error", "review_status", "repair_attempted", "fallback_used", "final_status"]
    missing = [k for k in required if k not in data]
    if missing:
        print(f"MISSING KEYS: {missing}")
        return 1
    print(f"all 8 required keys present: OK")

    print(f"\ncontent_blocks count: {len(data['content_blocks'])}")
    if data["content_blocks"]:
        first = data["content_blocks"][0]
        if isinstance(first, dict):
            print(f"first block keys: {list(first.keys())}")
            heading = first.get("heading") or first.get("title") or first.get("type", "<no heading>")
            print(f"first block heading: {heading!r}")
            text_field = first.get("content") or first.get("body") or first.get("text", "")
            if isinstance(text_field, str):
                print(f"first block content[:120]: {text_field[:120]!r}")

    print(f"\nquestions count: {len(data['questions'])}")
    print(f"response[:120]: {data['response'][:120]!r}")
    print(f"error: {data['error']!r}")
    print(f"review_status: {data['review_status']!r}")
    print(f"repair_attempted: {data['repair_attempted']!r}")
    print(f"fallback_used: {data['fallback_used']!r}")
    print(f"final_status: {data['final_status']!r}")

    if data["error"]:
        print(f"\nFAIL: error field non-empty: {data['error']!r}")
        return 1
    if data["final_status"] != "success":
        print(f"\nFAIL: final_status != 'success' (got {data['final_status']!r})")
        return 1

    print("\nALL CHECKS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
