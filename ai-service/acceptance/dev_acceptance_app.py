"""Task 4 真实 SSE 验收专用 ASGI 入口（仅本地启动验收使用，不修改生产装配）。

内部 API 暴露方式与生产 uvicorn 启动方式一致：把 internal_api.router 装进 FastAPI。
"""
from fastapi import FastAPI

from internal_api import router

app = FastAPI(title="ai-inference-acceptance")
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "ai-inference"}
