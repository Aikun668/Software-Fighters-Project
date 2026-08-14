"""A/B 对照：httpx vs aiohttp 调 deepseek API"""
import asyncio, os, json, time
from dotenv import load_dotenv
load_dotenv()
import httpx, aiohttp

URL = os.getenv("DEEPSEEK_BASE_URL", "") + "/chat/completions"
KEY = os.getenv("DEEPSEEK_API_KEY", "").split(",")[0].strip()
PAYLOAD = {
    "model": "deepseek-v4-pro",
    "messages": [{"role": "user", "content": '输出 {"ok": true}'}],
    "temperature": 0.0, "max_tokens": 32, "stream": False,
}
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

N_SEQ = 5  # 连续发 N 次


async def test_sequential():
    print(f"=== 串行 {N_SEQ} 次请求 ===\n")

    # ── httpx (shared client) ──
    print("--- httpx (shared client) ---")
    t0 = time.perf_counter()
    httpx_ok = 0
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0)) as client:
        for i in range(N_SEQ):
            try:
                resp = await client.post(URL, json=PAYLOAD, headers=HEADERS)
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                ok = len(content) > 2
                if ok:
                    httpx_ok += 1
                print(f"  [{i+1}] status={resp.status_code} ok={ok} content={repr(content[:40])}")
            except Exception as e:
                print(f"  [{i+1}] FAIL: {type(e).__name__}: {str(e)[:100]}")
            await asyncio.sleep(0.3)
    t1 = time.perf_counter()
    print(f"  结果: {httpx_ok}/{N_SEQ} OK ({t1-t0:.1f}s)\n")

    # ── aiohttp (fresh session) ──
    print("--- aiohttp (fresh session each) ---")
    t0 = time.perf_counter()
    aio_ok = 0
    for i in range(N_SEQ):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                async with s.post(URL, json=PAYLOAD, headers=HEADERS) as resp:
                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"]
                    ok = len(content) > 2
                    if ok:
                        aio_ok += 1
                    print(f"  [{i+1}] status={resp.status} ok={ok} content={repr(content[:40])}")
        except Exception as e:
            print(f"  [{i+1}] FAIL: {type(e).__name__}: {str(e)[:100]}")
        await asyncio.sleep(0.3)
    t1 = time.perf_counter()
    print(f"  结果: {aio_ok}/{N_SEQ} OK ({t1-t0:.1f}s)\n")


async def test_concurrent():
    print(f"=== 并发 4 请求 ===\n")

    # ── httpx ──
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0)) as client:

        async def httpx_one(i):
            try:
                resp = await client.post(URL, json=PAYLOAD, headers=HEADERS)
                data = resp.json()
                return "OK", len(data["choices"][0]["message"]["content"])
            except Exception as e:
                return "FAIL", f"{type(e).__name__}: {str(e)[:60]}"

        hr = await asyncio.gather(*[httpx_one(i) for i in range(4)])
    h_ok = sum(1 for r in hr if r[0] == "OK")
    print(f"  httpx: {h_ok}/4 OK  {hr}")

    # ── aiohttp ──
    async def aiohttp_one(i):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                async with s.post(URL, json=PAYLOAD, headers=HEADERS) as resp:
                    data = await resp.json()
                    return "OK", len(data["choices"][0]["message"]["content"])
        except Exception as e:
            return "FAIL", f"{type(e).__name__}: {str(e)[:60]}"

    ar = await asyncio.gather(*[aiohttp_one(i) for i in range(4)])
    a_ok = sum(1 for r in ar if r[0] == "OK")
    print(f"  aiohttp: {a_ok}/4 OK  {ar}")


async def main():
    await test_sequential()
    await asyncio.sleep(1)
    await test_concurrent()


if __name__ == "__main__":
    asyncio.run(main())
