"""验证生产语义腿（use_mock=False）用 8 类 prompt 后能识别冷门意图。"""
import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
AI = os.path.abspath(os.path.join(HERE, "..", "..", "..", "ai-service"))
sys.path.insert(0, AI)

from dotenv import load_dotenv
load_dotenv(os.path.join(AI, ".env"))

from app.services.intent_extractor import IntentExtractor  # noqa: E402

SAMPLE = [
    "帮我解一下这道题，求sinx除以x的极限",
    "证明根号2是无理数",
    "给我一个快速排序的代码示例",
    "帮我生成关于操作系统的闪卡",
    "给我出5道进程调度选择题",
    "什么是进程调度",
]


async def main():
    ex = IntentExtractor(use_mock=False)
    for msg in SAMPLE:
        r = await ex.extract_multi(msg, max_intents=2)
        intents = [(i.intent, round(i.confidence, 2)) for i in r.intents]
        print(f"{msg[:22]:<22} -> {intents}")


asyncio.run(main())
