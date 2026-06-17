"""四通道 LLM 连接性测试"""
import asyncio, os, sys, unicodedata
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))
from app.services.llm_service import OpenAILLM


def safe_str(s: str, limit: int = 80) -> str:
    """剔除非 ASCII 字符，安全输出到 GBK 终端。"""
    s = s.strip()
    if len(s) > limit:
        s = s[:limit] + "..."
    return s.encode("ascii", errors="replace").decode("ascii")


CHANNELS = [
    {
        "name": "[pro] deepseek-v4-pro",
        "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
        "base_url": os.getenv("DEEPSEEK_BASE_URL", ""),
        "model": "deepseek-v4-pro",
        "temperature": 0.0,
        "max_tokens": 32,
    },
    {
        "name": "[plus] qwen3.7-plus",
        "api_key": os.getenv("DASHSCOPE_API_KEY_PLUS", ""),
        "base_url": os.getenv("DASHSCOPE_BASE_URL", ""),
        "model": "qwen3.7-plus",
        "temperature": 0.0,
        "max_tokens": 32,
    },
    {
        "name": "[flash] deepseek-v4-flash",
        "api_key": os.getenv("DASHSCOPE_API_KEY_FLASH", ""),
        "base_url": os.getenv("DASHSCOPE_BASE_URL", ""),
        "model": "deepseek-v4-flash",
        "temperature": 0.0,
        "max_tokens": 32,
    },
    {
        "name": "[max] qwen3.7-max",
        "api_key": os.getenv("DASHSCOPE_API_KEY_MAX", ""),
        "base_url": os.getenv("DASHSCOPE_BASE_URL", ""),
        "model": "qwen3.7-max-2026-05-17",
        "temperature": 0.0,
        "max_tokens": 32,
    },
]


async def test_one(ch: dict) -> tuple[str, bool, str]:
    llm = OpenAILLM(
        api_key=ch["api_key"],
        base_url=ch["base_url"],
        model=ch["model"],
        temperature=ch["temperature"],
        max_tokens=ch["max_tokens"],
    )
    try:
        resp = await llm.chat([{"role": "user", "content": "回复 OK"}])
        return ch["name"], True, resp.strip()[:80]
    except Exception as e:
        return ch["name"], False, str(e)[:120]


async def main():
    print("=" * 60)
    print("四通道 LLM 连接性测试")
    print("=" * 60)
    tasks = [test_one(c) for c in CHANNELS]
    results = await asyncio.gather(*tasks)

    ok = 0
    fail = 0
    for name, success, msg in results:
        status = "[PASS]" if success else "[FAIL]"
        preview = safe_str(msg)
        print(f"\n{name}")
        print(f"  {status}  ->  {preview}")
        if success:
            ok += 1
        else:
            fail += 1

    print(f"\n{'=' * 60}")
    print(f"结果: {ok}/{len(CHANNELS)} 通过, {fail}/{len(CHANNELS)} 失败")
    print("=" * 60)
    return fail == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
