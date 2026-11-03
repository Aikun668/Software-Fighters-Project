"""验证真模型语义腿对复合句的多意图识别能力。"""
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
    "解释一下什么是B+树，然后出5道题",
    "先帮我讲讲快排，再给我几道练习题",
    "给我一份讲义，外加10道练习题",
    "生成一份思维导图，再出几道题",
    "什么是死锁，顺便出几道题考考我",
]


async def main():
    ex = IntentExtractor(use_mock=False)
    for msg in SAMPLE:
        r = await ex.extract_multi(msg, max_intents=3)
        intents = [(i.intent, round(i.confidence, 3)) for i in r.intents]
        print(f"{msg[:24]:<24} -> {intents}")


asyncio.run(main())
