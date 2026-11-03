"""验证真模型（8类 prompt）对「产物变换」类短指代句的判断。

关键：这些短句脱离 history 无法判断，看真模型单独判会出什么，以及带语境能否判对。
"""
import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
AI = os.path.abspath(os.path.join(HERE, "..", "..", "..", "ai-service"))
sys.path.insert(0, AI)

from dotenv import load_dotenv
load_dotenv(os.path.join(AI, ".env"))

from app.services.intent_extractor import IntentExtractor  # noqa: E402

# (当前短句, 上轮语境描述) —— 验证「单句」和「带语境」两种判断
CASES = [
    ("给我个代码实现", "上轮用户问动态规划概念"),
    ("难度调高一点", "上轮系统出了几道题"),
    ("有没有配套的练习题", "上轮系统生成了一份学习资源"),
    ("帮我整理成一张图", "上轮系统讲解了一个概念"),
    ("对，我就是想转行", "上轮在讨论职业规划"),
]


async def main():
    ex = IntentExtractor(use_mock=False)
    print("=== 单句判断（无语境）===")
    for msg, _ in CASES:
        r = await ex.extract_multi(msg, max_intents=2)
        print(f"  {msg[:18]:<18} -> {[(i.intent, round(i.confidence,2)) for i in r.intents]}")

    print("\n=== 带语境判断（拼上轮上下文）===")
    for msg, prev in CASES:
        combined = f"{prev}。现在用户说：{msg}"
        r = await ex.extract_multi(combined, max_intents=2)
        print(f"  {msg[:18]:<18} -> {[(i.intent, round(i.confidence,2)) for i in r.intents]}")


asyncio.run(main())
