"""internal_api 包内的无状态小工具（非路由、非装配）。

这些函数不被任何测试 patch，故子模块可直接 import，无需 `api.` 限定。
"""


def _sse_stream_chunks(text: str, size: int = 4):
    """将文本按固定大小切分为块生成器，用于 SSE token 流。"""
    for i in range(0, len(text), size):
        yield text[i:i + size]
