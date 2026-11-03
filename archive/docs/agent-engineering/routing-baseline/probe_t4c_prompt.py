"""T4-C 探针：对比 5 类 vs 8 类 prompt 对冷门意图的识别能力（真调采样，用户已授权）。

不改生产 EXTRACTION_PROMPT；构造 8 类 prompt 变体，真调同一批冷门消息，
对比两类 prompt 的意图识别结果。用数据决定是否扩展 prompt。
"""
import asyncio
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
AI = os.path.abspath(os.path.join(HERE, "..", "..", "..", "ai-service"))
sys.path.insert(0, AI)

from dotenv import load_dotenv
load_dotenv(os.path.join(AI, ".env"))

from app.services.llm_service import get_llm_service  # noqa: E402
from app.utils.json_parser import parse_llm_json  # noqa: E402

PROMPT_5 = """分析用户消息，判断其意图类别。返回JSON。
规则：
1. 只提取用户明确表达的意图，不推测
2. 单意图消息只输出一个意图，多诉求消息才输出多个
3. 不确定时用 tutor_question 兜底
意图类别（5类）：
1. tutor_question - 答疑/概念解释
2. resource_gen - 生成学习资源（教程/文档/代码/闪卡/思维导图/项目）
3. exercise_gen - 生成练习题/出题/做题
4. learning_path - 学习路径规划
5. visualize - 画图/可视化/流程图/知识图谱
返回格式：{"intents":[{"intent":"exercise_gen","params":{"topic":"..."},"confidence":0.95}],"is_clear":true}"""

PROMPT_8 = """分析用户消息，判断其意图类别。返回JSON。
规则：
1. 只提取用户明确表达的意图，不推测
2. 单意图消息只输出一个意图，多诉求消息才输出多个
3. 不确定时用 tutor_question 兜底
意图类别（8类）：
1. tutor_question - 答疑/概念解释/闲聊
2. solve_problem - 解一道具体题目（求解/计算/证明/推导/这道题怎么做）
3. code_example - 要代码示例（写代码/代码实现/给个例子/示例）
4. flashcard_gen - 要记忆闪卡（闪卡/记忆卡/背诵）
5. resource_gen - 生成学习资源（教程/文档/讲义/课件）
6. exercise_gen - 生成练习题/出题/做题
7. learning_path - 学习路径规划/怎么学
8. visualize - 画图/流程图/示意图
返回格式：{"intents":[{"intent":"exercise_gen","params":{"topic":"..."},"confidence":0.95}],"is_clear":true}"""

# 冷门意图采样（solve/code/flashcard 为主）
SAMPLE = [
    "帮我解一下这道题，求sinx除以x在x趋近于0时的极限",
    "这道物理题怎么做，落地速度多少",
    "证明根号2是无理数",
    "给我一个快速排序的代码示例",
    "给我个代码实现",
    "解释一下动态规划，给我个代码示例",
    "帮我生成关于操作系统进程的闪卡",
    "帮我做几张英语单词的闪卡",
    "出5道题，顺便把知识点做成知识图谱",
    "帮我画一张TCP三次握手流程图",
    "什么是进程调度",
    "给我出5道进程调度选择题",
]


async def run(prompt, label):
    llm = get_llm_service()
    print(f"\n===== {label} =====")
    lat = []
    for msg in SAMPLE:
        t = time.perf_counter()
        try:
            resp = await llm.chat([{"role": "user", "content": prompt + f"\n\n用户消息：{msg}\n\n解析意图，返回JSON："}])
            data = parse_llm_json(resp, fallback={}, expected_key="intents")
            intents = [it.get("intent", "?") for it in data.get("intents", [])] if isinstance(data, dict) else "?"
        except Exception as e:
            intents = f"EXC:{type(e).__name__}"
        dt = (time.perf_counter() - t) * 1000
        lat.append(dt)
        print(f"[{dt:6.0f}ms] {msg[:20]:<20} -> {intents}")
    lat.sort()
    n = len(lat)
    print(f"p50={lat[n//2]:.0f}ms p95={lat[min(n-1,int(n*0.95))]:.0f}ms max={max(lat):.0f}ms")


async def main():
    await run(PROMPT_5, "5类 prompt")
    await run(PROMPT_8, "8类 prompt")


asyncio.run(main())
