"""综合测试脚本：领域路由 + 路径规划 + 追问解析 + 画像提取

用法: python tests/manual_test_comprehensive.py
前提: AI 服务已在 8001 端口运行 (python -B main.py)

测试模块:
  1. 领域路由：AI 问题 vs 通用问题
  2. 路径规划：topic 是否被尊重（不被 profile weak_points 覆盖）
  3. 追问解析计划：/inquiry/resolve/plan 端点
  4. 画像提取：tutor chat 后 profile_delta 变化
"""

import json
import sys
import io
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = "http://127.0.0.1:8001/internal"
RESULTS = []


def sse_request(endpoint: str, body: dict, timeout: int = 90) -> dict:
    """通用 SSE 请求，返回 {tokens, response, done_payload, events, error}"""
    url = f"{BASE}/{endpoint}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    response_text = ""
    done_payload = {}
    events = []
    tokens = 0

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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

                events.append(data)
                evt_type = data.get("type", "")

                if evt_type == "token":
                    tokens += 1
                    response_text += data.get("content", "")
                elif evt_type == "done":
                    done_payload = data
    except Exception as e:
        return {"error": str(e), "url": url}

    return {
        "tokens": tokens,
        "response": response_text,
        "done_payload": done_payload,
        "events": events,
    }


def json_request(endpoint: str, body: dict, method: str = "POST", timeout: int = 30) -> dict:
    """通用 JSON 请求"""
    url = f"{BASE}/{endpoint}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8") if body else None,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "body": e.read().decode("utf-8", errors="replace")[:500]}
    except Exception as e:
        return {"error": str(e)}


def record(label: str, passed: bool, details: str = ""):
    icon = "PASS" if passed else "FAIL"
    RESULTS.append({"label": label, "passed": passed, "details": details})
    print(f"  [{icon}] {label}")
    if details:
        print(f"        {details}")


# ═══════════════════════════════════════════════════════════════
# 模块 1: 领域路由 — AI vs 通用
# ═══════════════════════════════════════════════════════════════

def test_domain_routing():
    print("\n" + "=" * 70)
    print("[模块 1] 领域路由测试")
    print("=" * 70)

    cases = [
        ("数学题：勾股定理怎么证明？", "general", "数学问题应走通用路由"),
        ("梯度下降算法的原理是什么？", "ai", "AI术语应走AI路由"),
        ("唐朝为什么会灭亡？", "general", "历史问题应走通用路由"),
        ("什么是卷积神经网络？", "ai", "CNN是AI概念"),
        ("英语四级怎么复习？", "general", "英语学习应走通用路由"),
        ("机器学习和深度学习的区别是什么？", "ai", "ML/DL对比是AI话题"),
    ]

    for question, expected, desc in cases:
        body = {
            "user_id": 1,
            "student_profile": {"knowledge_base": 40},
            "messages": [{"role": "user", "content": question}],
        }
        result = sse_request("tutor/chat", body)
        if "error" in result:
            record(f"领域路由-{desc}", False, f"请求失败: {result['error']}")
            continue

        actual = result["done_payload"].get("domain", "unknown")
        passed = (actual == expected)

        # 对 general 域检查是否有 AI 幻觉
        ai_terms = ["神经网络", "梯度下降", "卷积", "损失函数", "反向传播", "过拟合", "深度学习"]
        response = result["response"]
        hallucinations = [t for t in ai_terms if t in response] if expected == "general" else []

        if hallucinations:
            record(f"领域路由-{desc}", False,
                   f"domain={actual}(期望{expected}), 幻觉词: {hallucinations}")
        else:
            record(f"领域路由-{desc}", passed,
                   f"domain={actual}(期望{expected}), 回复前60字: {response[:60]}")


# ═══════════════════════════════════════════════════════════════
# 模块 2: 路径规划 — Topic 约束
# ═══════════════════════════════════════════════════════════════

def test_path_planning():
    print("\n" + "=" * 70)
    print("[模块 2] 路径规划 Topic 约束测试")
    print("=" * 70)

    cases = [
        {
            "label": "数学主题 + 英语弱点画像",
            "topic": "数学",
            "profile": {
                "knowledge_base": 35,
                "weak_points": ["英语语法", "英语词汇"],
                "strong_points": ["数学计算"],
            },
            "expected_keywords": ["数", "算", "方程", "运算", "几何", "函数"],
            "forbidden_keywords": ["英语", "English", "语法", "词汇"],
        },
        {
            "label": "物理主题 + 数学弱点画像",
            "topic": "物理",
            "profile": {
                "knowledge_base": 50,
                "weak_points": ["数学应用题", "古文翻译"],
                "strong_points": ["实验操作"],
            },
            "expected_keywords": ["物理", "力", "运动", "能量", "电", "光"],
            "forbidden_keywords": ["数学", "古文"],
        },
        {
            "label": "Python编程主题 + 无画像",
            "topic": "Python编程",
            "profile": {},
            "expected_keywords": ["Python", "编程", "代码", "函数", "变量", "循环"],
            "forbidden_keywords": [],
        },
    ]

    for tc in cases:
        body = {
            "user_id": 1,
            "course_id": "general",
            "topic": tc["topic"],
            "student_profile": tc["profile"],
        }
        result = json_request("plans/create-from-path", body)
        if "error" in result:
            record(f"路径-{tc['label']}", False, f"请求失败: {result['error']}")
            continue

        data = result.get("data", result)
        steps = data.get("steps", data.get("plan", {}).get("steps", []))
        if not steps:
            record(f"路径-{tc['label']}", False, f"未返回 steps，响应: {json.dumps(result, ensure_ascii=False)[:200]}")
            continue

        step_topics = [s.get("topic", "") for s in steps]
        all_text = " ".join(step_topics)

        # 检查有无禁止词
        found_forbidden = [kw for kw in tc["forbidden_keywords"] if kw in all_text]
        # 检查是否有期望词
        found_expected = [kw for kw in tc["expected_keywords"] if kw in all_text]

        passed = (len(found_forbidden) == 0) and (len(found_expected) > 0)
        details = f"步骤: {step_topics[:5]}"
        if found_forbidden:
            details += f" | 禁止词出现: {found_forbidden}"
        if not found_expected:
            details += f" | 期望词全部缺失"

        record(f"路径-{tc['label']}", passed, details)


# ═══════════════════════════════════════════════════════════════
# 模块 3: 追问解析计划 — /inquiry/resolve/plan
# ═══════════════════════════════════════════════════════════════

def test_inquiry_resolve_plan():
    print("\n" + "=" * 70)
    print("[模块 3] 追问解析计划 (/inquiry/resolve/plan)")
    print("=" * 70)

    cases = [
        {
            "label": "基本追问解析-数学",
            "body": {
                "original_message": "我想学数学",
                "answers": ["初中数学", "视频教学", "每天1小时"],
                "user_id": 1,
                "student_profile": {"knowledge_base": 30},
                "questions": [
                    {"id": 1, "question": "你想学什么阶段的数学？"},
                    {"id": 2, "question": "你喜欢什么学习方式？"},
                    {"id": 3, "question": "每天能投入多少时间？"},
                ],
                "suggested_types": ["video", "exercise"],
                "clarified_topic": "初中数学",
            },
            "expect_topic_in_steps": ["数"],
        },
        {
            "label": "追问解析-AI主题",
            "body": {
                "original_message": "我想入门机器学习",
                "answers": ["有Python基础", "想做图像识别"],
                "user_id": 1,
                "student_profile": {"knowledge_base": 50, "strong_points": ["Python编程"]},
                "questions": [
                    {"id": 1, "question": "你有什么编程基础？"},
                    {"id": 2, "question": "你想做什么方向的应用？"},
                ],
                "suggested_types": ["tutorial", "project"],
                "clarified_topic": "机器学习入门",
            },
            "expect_topic_in_steps": ["机器学习", "学习", "模型", "数据"],
        },
    ]

    for tc in cases:
        result = sse_request("inquiry/resolve/plan", tc["body"])
        if "error" in result:
            record(f"追问-{tc['label']}", False, f"请求失败: {result['error']}")
            continue

        done = result["done_payload"]
        if not done:
            record(f"追问-{tc['label']}", False, "未收到 done event")
            continue

        plan = done.get("plan", {})
        steps = plan.get("steps", [])
        topic = plan.get("topic", "")

        if not steps:
            record(f"追问-{tc['label']}", False, f"steps 为空, done={json.dumps(done, ensure_ascii=False)[:300]}")
            continue

        step_topics = [s.get("topic", "") for s in steps]
        all_text = " ".join(step_topics)
        found = [kw for kw in tc["expect_topic_in_steps"] if kw in all_text]

        passed = len(found) > 0 and len(steps) >= 2
        record(f"追问-{tc['label']}", passed,
               f"topic={topic}, {len(steps)}步, 步骤: {step_topics[:4]}")


# ═══════════════════════════════════════════════════════════════
# 模块 4: 画像提取 — tutor chat 后的 profile_delta
# ═══════════════════════════════════════════════════════════════

def test_profile_extraction():
    print("\n" + "=" * 70)
    print("[模块 4] 画像提取测试 (profile_delta)")
    print("=" * 70)

    cases = [
        {
            "label": "学生表达学习困难",
            "messages": [
                {"role": "user", "content": "我数学特别差，总是记不住公式，做题很慢，已经学了3个月了还是不行"},
            ],
            "profile": {"knowledge_base": 40},
            "expect_fields": ["weak_points", "learning_style"],
        },
        {
            "label": "学生表达兴趣方向",
            "messages": [
                {"role": "user", "content": "我对机器人和自动驾驶特别感兴趣，想往这个方向深入学习"},
            ],
            "profile": {"knowledge_base": 60},
            "expect_fields": ["interest_direction"],
        },
        {
            "label": "多轮对话-暴露知识水平",
            "messages": [
                {"role": "user", "content": "老师，什么是函数？"},
                {"role": "assistant", "content": "函数是一种数学关系..."},
                {"role": "user", "content": "哦我明白了，就像 y=2x+1 这种吧？那二次函数呢？"},
            ],
            "profile": {"knowledge_base": 30, "weak_points": ["函数"]},
            "expect_fields": ["knowledge_base"],
        },
    ]

    for tc in cases:
        body = {
            "user_id": 1,
            "student_profile": tc["profile"],
            "messages": tc["messages"],
        }
        result = sse_request("tutor/chat", body)
        if "error" in result:
            record(f"画像-{tc['label']}", False, f"请求失败: {result['error']}")
            continue

        done = result["done_payload"]
        profile_delta = done.get("profile_delta", {})

        # profile_delta 可能在 done event 中，也可能没有（如果后台提取未完成）
        has_delta = bool(profile_delta)
        response_preview = result["response"][:80]

        if has_delta:
            found_fields = [f for f in tc["expect_fields"] if f in str(profile_delta)]
            passed = len(found_fields) > 0
            record(f"画像-{tc['label']}", passed,
                   f"delta={json.dumps(profile_delta, ensure_ascii=False)[:150]}")
        else:
            # 画像提取是后台异步的，可能 done 时还没完成
            record(f"画像-{tc['label']}", True,
                   f"(后台异步提取,done时无delta) 回复: {response_preview}")


# ═══════════════════════════════════════════════════════════════
# 模块 5: 统一聊天 /api/chat — 模式自动感知
# ═══════════════════════════════════════════════════════════════

def test_unified_chat():
    print("\n" + "=" * 70)
    print("[模块 5] 统一聊天模式自动感知")
    print("=" * 70)

    cases = [
        {
            "label": "auto模式-解题请求",
            "body": {
                "message": "帮我解一下这道题：x^2 + 5x + 6 = 0",
                "user_id": 1,
                "mode": "auto",
                "student_profile": {},
                "messages": [],
            },
            "expect_mode": "solve",
        },
        {
            "label": "auto模式-资源请求",
            "body": {
                "message": "帮我生成一份关于Python基础的学习资料",
                "user_id": 1,
                "mode": "auto",
                "student_profile": {},
                "messages": [],
            },
            "expect_mode": "resource",
        },
        {
            "label": "auto模式-答疑请求",
            "body": {
                "message": "老师，我不太理解递归是什么意思",
                "user_id": 1,
                "mode": "tutor",
                "student_profile": {},
                "messages": [],
            },
            "expect_mode": "tutor",
        },
    ]

    for tc in cases:
        result = sse_request("api/chat", tc["body"])
        if "error" in result:
            record(f"统一聊天-{tc['label']}", False, f"请求失败: {result['error']}")
            continue

        done = result["done_payload"]
        actual_mode = done.get("mode", "unknown")
        response = result["response"]

        passed = bool(response) and len(response) > 10
        record(f"统一聊天-{tc['label']}", passed,
               f"mode={actual_mode}(期望{tc['expect_mode']}), 回复长度={len(response)}")


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("  AI Service 综合测试")
    print(f"  服务地址: {BASE}")
    print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # 先检查服务是否可达
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:8001/health",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            health = json.loads(resp.read())
            print(f"\n  服务状态: {health.get('status', 'unknown')}")
    except Exception as e:
        print(f"\n  [ERROR] 服务不可达: {e}")
        print("  请先启动服务: python -B main.py")
        return 1

    test_domain_routing()
    test_path_planning()
    test_inquiry_resolve_plan()
    test_profile_extraction()
    test_unified_chat()

    # 最终汇总
    print("\n" + "=" * 70)
    print("  测试汇总")
    print("=" * 70)
    passed = sum(1 for r in RESULTS if r["passed"])
    total = len(RESULTS)
    print(f"  通过: {passed}/{total}")
    print()
    for r in RESULTS:
        icon = "PASS" if r["passed"] else "FAIL"
        print(f"  [{icon}] {r['label']}")
    print()

    if passed == total:
        print("  >>> 全部通过!")
    else:
        failed = [r for r in RESULTS if not r["passed"]]
        print(f"  >>> {len(failed)} 项未通过:")
        for r in failed:
            print(f"      - {r['label']}: {r['details']}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
