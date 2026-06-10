"""验证领域路由 + 门控效果的快速测试脚本。

用法: python tests/manual_test_domain_router.py
前提: AI 服务已在 8001 端口运行 (python main.py)
"""

import json
import sys
import io
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = "http://127.0.0.1:8001/internal"

TEST_CASES = [
    {
        "label": "非AI-数学学习问题",
        "expected_domain": "general",
        "body": {
            "user_id": 1,
            "student_profile": {},
            "messages": [
                {"role": "user", "content": "我数学不好，喜欢看视频学数学，有什么建议吗？"}
            ],
        },
    },
    {
        "label": "AI-梯度下降问题",
        "expected_domain": "ai",
        "body": {
            "user_id": 1,
            "student_profile": {},
            "messages": [
                {"role": "user", "content": "什么是梯度下降？"}
            ],
        },
    },
    {
        "label": "非AI-历史问题",
        "expected_domain": "general",
        "body": {
            "user_id": 1,
            "student_profile": {},
            "messages": [
                {"role": "user", "content": "唐朝为什么灭亡了？"}
            ],
        },
    },
    {
        "label": "AI-神经网络问题",
        "expected_domain": "ai",
        "body": {
            "user_id": 1,
            "student_profile": {},
            "messages": [
                {"role": "user", "content": "神经网络的反向传播算法是怎么工作的？"}
            ],
        },
    },
    {
        "label": "边界-包含AI词汇但非AI领域",
        "expected_domain": "general",
        "body": {
            "user_id": 1,
            "student_profile": {},
            "messages": [
                {"role": "user", "content": "我学AI学得很痛苦，想退课了，怎么办？"}
            ],
        },
    },
]


def test_tutor_chat(label: str, body: dict) -> dict:
    """发送 SSE 请求，收集完整响应。"""
    req = urllib.request.Request(
        f"{BASE}/tutor/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    response_text = ""
    domain = ""
    tokens = 0

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            for line in resp:
                line = line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if not data_str:
                    continue
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                if data.get("type") == "token":
                    tokens += 1
                    response_text += data.get("content", "")
                elif data.get("type") == "done":
                    domain = data.get("domain", "")
    except Exception as e:
        return {"error": str(e), "label": label}

    # 检查是否有 AI 幻觉关键词
    ai_terms = ["神经网络", "梯度下降", "卷积", "计算机视觉", "损失函数",
                 "反向传播", "过拟合", "强化学习", "深度学习", "LSTM", "RNN"]
    hallucinations = [t for t in ai_terms if t in response_text]

    return {
        "label": label,
        "tokens": tokens,
        "response_preview": response_text[:200],
        "domain": domain,
        "hallucinations": hallucinations,
        "hallucination_free": len(hallucinations) == 0,
    }


def main():
    print("=" * 70)
    print("领域路由 + 门控效果测试")
    print("=" * 70)

    results = []
    for tc in TEST_CASES:
        label = tc["label"]
        expected = tc["expected_domain"]
        print(f"\n>> 测试: {label}")
        print(f"   期望领域: {expected}")

        result = test_tutor_chat(label, tc["body"])

        if "error" in result:
            print(f"   ❌ 请求失败: {result['error']}")
            results.append({"label": label, "status": "ERROR"})
            continue

        actual_domain = result.get("domain", "unknown")
        domain_match = (expected == actual_domain)
        h_free = result["hallucination_free"]

        print(f"   实际领域: {actual_domain} {'✅' if domain_match else '❌'}")
        print(f"   回复预览: {result['response_preview'][:100]}...")
        print(f"   Token 数: {result['tokens']}")

        if result["hallucinations"]:
            print(f"   ❌ 发现AI幻觉词: {result['hallucinations']}")
        else:
            print(f"   幻觉检查: ✅ 无AI术语泄露")

        results.append({
            "label": label,
            "expected": expected,
            "actual": actual_domain,
            "domain_match": domain_match,
            "hallucination_free": h_free,
        })

    # 总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)
    passed = sum(1 for r in results if r.get("domain_match") and r.get("hallucination_free"))
    total = len(results)
    print(f"  通过: {passed}/{total}")
    for r in results:
        icon = "✅" if (r.get("domain_match") and r.get("hallucination_free")) else "❌"
        print(f"  {icon} {r['label']}: expected={r.get('expected','?')}, actual={r.get('actual','?')}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
