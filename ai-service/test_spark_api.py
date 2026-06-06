"""
星火 API + BaseAgent 测试脚本

验证：
  1. 非流式调用
  2. 流式调用
  3. BaseAgent 和 SparkLLM 可正常 import

用法：
  python test_spark_api.py
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

load_dotenv(".env")

API_KEY = os.getenv("SPARK_API_KEY", "")
API_SECRET = os.getenv("SPARK_API_SECRET", "")


def check_api_key() -> bool:
    """检查 API Key 是否已配置"""
    if not API_KEY or API_KEY == "your_spark_api_key_here":
        print("❌ SPARK_API_KEY 未配置，请编辑 .env 填入真实的 Key")
        return False
    if not API_SECRET or API_SECRET == "your_spark_api_secret_here":
        print("❌ SPARK_API_SECRET 未配置，请编辑 .env 填入真实的 Secret")
        return False
    return True


def test_imports() -> bool:
    """测试关键模块可正常导入"""
    print("=" * 50)
    print("测试 0: 模块导入")
    print("=" * 50)
    try:
        from app.services.llm_service import SparkLLM
        print("  ✅ SparkLLM import OK")
    except Exception as e:
        print(f"  ❌ SparkLLM import 失败: {e}")
        return False

    try:
        from app.agents.base_agent import BaseAgent
        print("  ✅ BaseAgent import OK")
    except Exception as e:
        print(f"  ❌ BaseAgent import 失败: {e}")
        return False

    print()
    return True


async def test_non_streaming() -> bool:
    """测试非流式调用"""
    print("=" * 50)
    print("测试 1: 非流式调用")
    print("=" * 50)

    from app.services.llm_service import SparkLLM

    llm = SparkLLM(
        temperature=0.7,
        max_tokens=512,
    )

    messages = [{"role": "user", "content": "用一句话解释什么是多智能体系统"}]

    system_prompt = "你是一个有用的AI助手。"

    try:
        print("  → 发送请求...")
        response = await llm.chat(messages, system_prompt=system_prompt)
        content_len = len(response)
        preview = response[:120].replace("\n", " ")
        print(f"  ✅ 非流式调用成功")
        print(f"     返回长度: {content_len} 字符")
        print(f"     内容预览: {preview}...")
    except Exception as e:
        print(f"  ❌ 非流式调用失败: {e}")
        return False

    print()
    return True


async def test_streaming() -> bool:
    """测试流式调用"""
    print("=" * 50)
    print("测试 2: 流式调用")
    print("=" * 50)

    from app.services.llm_service import SparkLLM

    llm = SparkLLM(
        temperature=0.7,
        max_tokens=512,
    )

    messages = [{"role": "user", "content": "列出Python多智能体系统的三个关键组件"}]

    system_prompt = "你是一个有用的AI助手。"

    try:
        print("  → 发送流式请求...")
        token_count = 0
        full_content = ""

        async for chunk in llm.chat_stream(messages, system_prompt=system_prompt):
            token_count += 1
            full_content += chunk

        content_len = len(full_content)
        preview = full_content[:200].replace("\n", " ")
        print(f"  ✅ 流式调用成功")
        print(f"     Token 数: {token_count}")
        print(f"     总长度: {content_len} 字符")
        print(f"     内容预览: {preview}...")
    except Exception as e:
        print(f"  ❌ 流式调用失败: {e}")
        return False

    print()
    return True


async def main():
    print()
    print("╔══════════════════════════════════════════════╗")
    print("║      星火 API + BaseAgent 测试脚本           ║")
    print("╚══════════════════════════════════════════════╝")
    print()

    # Step 0: 检查 API Key
    if not check_api_key():
        print()
        print("请先配置 API Key，然后重新运行测试。")
        sys.exit(1)

    results = []

    # 测试 0: 导入
    results.append(("模块导入", test_imports()))

    # 测试 1: 非流式
    results.append(("非流式调用", await test_non_streaming()))

    # 测试 2: 流式
    results.append(("流式调用", await test_streaming()))

    # 汇总
    print("=" * 50)
    print("测试汇总")
    print("=" * 50)
    all_pass = True
    for name, passed in results:
        status = "✅" if passed else "❌"
        print(f"  {status} {name}")
        if not passed:
            all_pass = False

    print()
    if all_pass:
        print("🎉 全部通过！")
    else:
        print("⚠️  部分测试未通过，请检查上方错误信息。")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
