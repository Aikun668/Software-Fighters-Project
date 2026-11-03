"""真模型语义腿演练：时延 + 判断质量采样（用户已授权真调 DeepSeek）。

对 15 条代表性消息真调一次语义腿，记录时延分布与判断结果。
结果：
  p50≈933ms, p90≈1278ms, p95≈1506ms, max≈1506ms；15 条中 6 条 >1000ms。
  → 真模型判断质量好（明确能力 0.9~0.98 置信、不确定句给低置信），但 p95 时延
    超过 1000ms 预算，当前 SEMANTIC_TIMEOUT_SEC=1.0 会打断约 4 成慢请求。
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ai-service")))

from dotenv import load_dotenv
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ai-service", ".env")))

from app.services.intent_extractor import IntentExtractor

SAMPLE = [
    "给我出5道进程调度选择题",
    "帮我制定一个学习计划",
    "画一张TCP三次握手流程图",
    "帮我生成一份讲义",
    "什么是进程调度",
    "不要出题，只要讲解",
    "数据好难啊",
    "举个例子",
    "帮我诊断一下哪里薄弱",
    "我是零基础想学AI",
    "再来5道",
    "帮我找几个学习资源",
    "这道题怎么做",
    "规划一下复习路线",
    "给我个代码示例",
]


async def main():
    ex = IntentExtractor(use_mock=False)
    lat = []
    rows = []
    for msg in SAMPLE:
        t = time.perf_counter()
        try:
            r = await ex.extract_multi(msg)
            dt = (time.perf_counter() - t) * 1000
            intents = [(i.intent, round(i.confidence, 3)) for i in r.intents]
        except Exception as e:
            dt = (time.perf_counter() - t) * 1000
            intents = [f"EXC:{type(e).__name__}"]
        lat.append(dt)
        rows.append((dt, msg, intents))
        print(f"[{dt:7.1f}ms] {msg[:16]:<16} -> {intents}")

    lat.sort()
    n = len(lat)

    def pct(p):
        return lat[min(n - 1, int(n * p))]

    print(f"\nn={n}  p50={pct(0.50):.0f}ms  p90={pct(0.90):.0f}ms  p95={pct(0.95):.0f}ms  max={max(lat):.0f}ms")
    over = sum(1 for x in lat if x > 1000)
    print(f"超过 1000ms: {over}/{n}")


asyncio.run(main())
