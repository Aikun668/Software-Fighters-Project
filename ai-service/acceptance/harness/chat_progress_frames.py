"""聊天链路端到端指纹（**覆盖阶段 D 新增的 `progress` 帧**）。

为什么单独一个 harness：`sse_all_endpoints.py` 的聊天用例把 `_get_chat_center`
换成了 `_StubCenter`（只回放预置事件），因此**永远不产生图节点事件** ——
阶段 D 新增的 `progress` 帧在那个 harness 里**一条都测不到**（58 条存证全一致，
其实没覆盖它）。本文件**不 stub 任何 Center / Workflow**，跑真实链路：

    POST /internal/api/chat
      → ChatCenter.stream_chat
      → 真 ChatTaskDispatcher（token 泵 + progress 转发）
      → 真 TutorAgent 图（retrieve → respond）

⚠️ **本 harness 必须额外强制 LLM 走 mock**：聊天链路**未接** `AI_SERVICE_MOCK_LLM`
（`ChatCenter._get_dispatcher()` 直接 `DecomposeAgent()` / `TutorAgent()`，没带 mock 旗标，
与 `internal_api` 工厂的 `_get_mock_flag()` 口径不一致）→ 没有 API Key 的环境下，
整条链路**在构造期**就抛 `ValueError`。故只把 `create_llm` 的 `use_mock` 强制为 `True`；
其余（ChatCenter / ChatTaskDispatcher / TutorAgent 图 / SSE 装配）**全部真实**。

用法（在 ai-service 目录）：
    python -m acceptance.harness.chat_progress_frames after

设计：
- 指纹只取**稳定字段**：`(帧类型, stage, phase, token 文本)`；`done` 载荷含 DB 侧的
  会话/画像字段，不入指纹，避免跨环境漂移；
- 同时断言（不只打指纹）：progress 帧存在且 **started/completed 成对**、
  `done` 唯一且最后、token 正文非空；
- ⚠️ 真实链路可能向 DB 写入会话/消息/画像记录（与 `profile_pipeline.py` 同类）。
"""

import asyncio
import hashlib
import json
import os
import sys

# ⚠️ 必须在 import app.* 之前设置：工厂在构造时读这个开关
os.environ.setdefault("AI_SERVICE_MOCK_LLM", "1")

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import app.services.llm_service as _llm_service_module  # noqa: E402

_real_create_llm = _llm_service_module.create_llm
_real_openai_llm = _llm_service_module.OpenAILLM


class _MockForcedOpenAILLM(_real_openai_llm):
    """直接实例化的 LLM 也强制 mock（否则无 Key 环境在构造期就抛错）。"""

    def __init__(self, *args, **kwargs):
        kwargs["use_mock"] = True
        super().__init__(*args, **kwargs)


def _force_mock_create_llm(*args, **kwargs):
    """强制 mock：只让 LLM 离线，管道与图保持真实。"""
    kwargs["use_mock"] = True
    return _real_create_llm(*args, **kwargs)


def _patch_create_llm_everywhere() -> int:
    """把 `create_llm` 与 `OpenAILLM` 换成强制 mock 版。

    两处都要换，因为代码库里两条构造路径并存（都不认 `AI_SERVICE_MOCK_LLM`）：
    - `create_llm(...)`：被多个模块各自 `from ... import`；
    - `OpenAILLM(...)`：个别 Agent 直接实例化（如 `ProfileAgent.judge_llm`、
      `TutorAgent._get_clarity_llm`），且用的是**实例上的** `use_mock_llm`。

    `from` 导入是**绑定引用**，只改一处不生效。故：① 先换 `llm_service` 模块里的
    源头（此后新导入的模块自动拿到 mock 版）；② 再扫描**已加载**模块，把仍指向旧
    符号的引用一并对换。
    """
    patched = 0
    _llm_service_module.create_llm = _force_mock_create_llm
    _llm_service_module.OpenAILLM = _MockForcedOpenAILLM
    for module in list(sys.modules.values()):
        if getattr(module, "create_llm", None) is _real_create_llm:
            setattr(module, "create_llm", _force_mock_create_llm)
            patched += 1
        if getattr(module, "OpenAILLM", None) is _real_openai_llm:
            setattr(module, "OpenAILLM", _MockForcedOpenAILLM)
            patched += 1
    return patched


_patch_create_llm_everywhere()

from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from internal_api import router  # noqa: E402

# (case 名, 用户消息)：都走 auto → NORMAL_CHAT → TutorAgent（有两个图节点）
CASES = [
    ("tutor_normal_chat", "什么是进程？"),
    ("tutor_normal_chat_2", "用一句话解释反向传播"),
]


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _frames(text: str) -> list[dict]:
    """把 SSE 响应文本解析成事件字典列表（忽略 `:heartbeat` 等注释行）。"""
    out: list[dict] = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: "):]
        try:
            out.append(json.loads(payload))
        except ValueError:
            out.append({"type": "__unparsable__", "raw": payload})
    return out


def _fingerprint(frames: list[dict]) -> str:
    """稳定指纹：只含帧类型 / stage / phase / token 文本，跨环境可复跑。"""
    parts: list[str] = []
    for frame in frames:
        kind = frame.get("type")
        if kind == "token":
            parts.append(f"token:{frame.get('content')}")
        elif kind == "progress":
            phase = (frame.get("data") or {}).get("phase")
            parts.append(f"progress:{frame.get('stage')}:{phase}")
        elif kind in ("center_start", "center_end"):
            parts.append(f"{kind}:{frame.get('stage')}")
        elif kind == "done":
            parts.append("done")
        elif kind == "error":
            parts.append(f"error:{frame.get('content') or frame.get('message')}")
        else:
            parts.append(str(kind))
    return "\n".join(parts)


async def main(label: str) -> int:
    blocks: list[str] = []
    app = _make_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://accept", timeout=180.0,
    ) as client:
        for name, message in CASES:
            response = await client.post("/internal/api/chat", json={
                "message": message,
                "user_id": 1,
                "mode": "auto",
                "messages": [],
                "student_profile": {},
            })

            frames = _frames(response.text)
            types = [f.get("type") for f in frames]
            progress = [f for f in frames if f.get("type") == "progress"]
            phases = [(f.get("data") or {}).get("phase") for f in progress]
            tokens = "".join(
                str(f.get("content") or "") for f in frames if f.get("type") == "token"
            )

            problems: list[str] = []
            if response.status_code != 200:
                problems.append(f"status={response.status_code}")
            if not progress:
                problems.append("没有 progress 帧（阶段 D 的进度未上流）")
            if "started" not in phases or "completed" not in phases:
                problems.append(f"progress 未成对（started/completed）：{phases}")
            if not tokens.strip():
                problems.append("token 正文为空")
            if types.count("done") != 1 or (types and types[-1] != "done"):
                problems.append(f"done 不唯一或非最后一帧：count={types.count('done')}")

            fingerprint = _fingerprint(frames)
            digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
            blocks.append(
                f"### {name}\n"
                f"status={response.status_code}\n"
                f"frames={len(frames)} tokens={types.count('token')} "
                f"progress={len(progress)}\n"
                f"progress_stages={sorted({f.get('stage') for f in progress})}\n"
                f"types={types}\n"
                f"token_text={tokens[:160]!r}\n"
                f"problems={problems}\n"
                f"sha256={digest}\n"
                f"{fingerprint}\n"
            )

    report = "\n".join(blocks)
    with open(f"_accept_chat_progress_{label}.txt", "w", encoding="utf-8") as handle:
        handle.write(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "after")))
