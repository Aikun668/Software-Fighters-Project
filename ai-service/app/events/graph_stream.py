"""LangGraph 执行流 → 统一事件（流式阶段 C 的**转换层**）。

依据《流式系统演进与改造指导》阶段 C 的迁移规则：
1. 先选一条稳定链路试点（→ C3）；
2. **保留 `ainvoke` 旧路径作为回退**（本层提供等价替换，由 `GS-A02` 锁定）；
3. 把 Graph 流转成**内部统一事件**，不让前端依赖 LangGraph 的事件格式；
4. 验证一致性（→ C4）；5. 再扩展（→ C5）。

设计由最小实验（`tests/test_langgraph_stream_spike.py`）的实测结论决定：

| 实测 | 对本层的影响 |
|---|---|
| `updates` + `subgraphs=True` 能看到**内层（手工嵌套 `ainvoke`）节点**并带 namespace | 无需重写现有嵌套结构即可拿到分层节点事件 |
| `messages` 模式抓不到本项目自研 LLM 包装（`OpenAILLM`）的 token | **token 仍走既有旁路**（`current_on_token`），本层只管节点/状态事件 |
| `astream` 终态与 `ainvoke` 一致 | 可安全做等价替换 + 回退 |
| `debug` 模式的 `type == "task"` 事件 = **节点开始**，且带与 `updates` **同形**的 namespace | 阶段 D 据此补 `node.started`（`GS-A08`），**不必**逐节点改 `custom` writer |

⚠️ 本层**不改任何传输字节**：只发内部事件，不参与 SSE 帧构造。
`token` / `message.delta` 仍由既有 token 泵负责（见 `app/events/stream.py` 的说明）。
"""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from typing import Any

from app.events.stream import ProgressEventType, StreamEmitter

logger = logging.getLogger(__name__)

#: 标记「当前协程里已有一条图流在跑」——用于保证**只有最外层开流**。
#:
#: 为什么必须这样：内层（Workflow 节点里 `await agent.run()`）如果也开 `astream`，
#: 它拿到的 chunk 会被父级的 namespace 前缀污染，导致取不到自己的顶层 `values`
#: 快照（实测：会走到回退分支）。而内层**不开流也不会丢事件** —— 外层
#: `subgraphs=True` 本来就能看到内层节点（最小实验 `SP-05` 已证）。
_streaming_active: ContextVar[bool] = ContextVar("graph_stream_active", default=False)

#: 多模式 + 子图时使用的流模式组合
#:
#: - `updates` → 节点**完成**（`node.completed`）；
#: - `values`  → 顶层终态快照（返回值来源）；
#: - `debug`   → 节点**开始**（`type == "task"`，阶段 D 起用于 `node.started`）。
#:   `debug` 每节点多一个 chunk，但只读 `payload["name"]`（不落地/不序列化大载荷）。
DEFAULT_STREAM_MODES: tuple[str, ...] = ("updates", "values", "debug")

#: 图流总开关（**默认开启**；显式设 `0/false/no/off` 可整条退回 `ainvoke` 纯路径）
GRAPH_STREAM_ENV = "AI_SERVICE_GRAPH_STREAM"


def graph_stream_enabled() -> bool:
    """是否把 LangGraph 执行流接入统一事件层。

    默认开启（此时执行走 `astream`，但返回值与 `ainvoke` 等价，见 `GS-A02`）；
    设 `AI_SERVICE_GRAPH_STREAM=0` 可一键退回旧路径（回退开关，用于排障）。
    """
    return os.getenv(GRAPH_STREAM_ENV, "1").strip().lower() not in {
        "0", "false", "no", "off",
    }


def _chunk_parts(chunk: Any) -> tuple[tuple[str, ...], str | None, Any]:
    """把 astream 的产出归一化为 `(namespace, mode, data)`。

    形状随参数变化：
    - `subgraphs=True` + 多模式 → `(namespace, mode, data)`
    - 多模式（不含子图）→ `(mode, data)`
    - 单模式 → `data`
    """
    if isinstance(chunk, tuple):
        if len(chunk) == 3:
            namespace, mode, data = chunk
            return tuple(namespace or ()), mode, data
        if len(chunk) == 2:
            mode, data = chunk
            return (), mode, data
    return (), None, chunk


def _namespace_path(namespace: tuple[str, ...]) -> list[str]:
    """命名空间归一化为字符串列表（LangGraph 可能给 str 或 tuple）。"""
    return [str(part) for part in namespace]


async def ainvoke_with_events(
    compiled_graph,
    input_state: dict,
    *,
    emitter: StreamEmitter | None = None,
    config: dict | None = None,
) -> dict:
    """**等价于** `compiled_graph.ainvoke(input_state)`，但顺带发出节点事件。

    - `updates` 模式 → 每个节点完成时发一条 `node.completed`
      （带 `node` 名、`namespace` 层级路径、`depth` 层级深度）；
    - `values` 模式 → 取**顶层**最后一次快照作为返回值，与 `ainvoke` 语义一致；
    - 不传 `emitter` 时**直接走 `ainvoke`**（零额外开销，既有调用点可无脑替换）；
    - 订阅者异常被 `StreamEmitter` 隔离，不影响本次执行；
    - 图未产出顶层 `values`（疑似被中断）→ **抛错，绝不重跑**（`GS-A07`）。

    Args:
        compiled_graph: 已编译的 LangGraph 图（`compile()` 的产物）。
        input_state: 初始状态。
        emitter: 事件源；`None` 表示只要结果、不要事件。
        config: 透传给 LangGraph 的 config（如 `{"recursion_limit": ...}`）。

    Returns:
        终态字典，与 `compiled_graph.ainvoke(input_state)` 逐字段一致。
    """
    if emitter is None or _streaming_active.get():
        # 无事件源，或已有一条外层图流在跑（内层只需普通执行，节点事件由外层捕获）
        return await compiled_graph.ainvoke(input_state, config)

    final_state: dict | None = None
    active_token = _streaming_active.set(True)
    try:
        async for chunk in compiled_graph.astream(
            input_state,
            config=config,
            stream_mode=list(DEFAULT_STREAM_MODES),
            subgraphs=True,
        ):
            namespace, mode, data = _chunk_parts(chunk)

            if mode == "values":
                # 只认顶层快照；内层子图的 values 不是本次调用的返回值
                if not namespace and isinstance(data, dict):
                    final_state = data
                continue

            if mode == "updates" and isinstance(data, dict):
                path = _namespace_path(namespace)
                for node_name in data:
                    emitter.emit(
                        ProgressEventType.NODE_COMPLETED,
                        node=str(node_name),
                        namespace=path,
                        depth=len(path),
                    )
                continue

            if mode == "debug" and isinstance(data, dict):
                # 节点开始（阶段 D）：`debug` 流的 `task` 事件。其余 debug 类型
                # （`task_result` / `checkpoint` 等）本层不需要 —— `updates` 已给完成事件。
                if data.get("type") == "task":
                    node_name = (data.get("payload") or {}).get("name")
                    if node_name:
                        path = _namespace_path(namespace)
                        emitter.emit(
                            ProgressEventType.NODE_STARTED,
                            node=str(node_name),
                            namespace=path,
                            depth=len(path),
                        )
    finally:
        _streaming_active.reset(active_token)

    if final_state is None:
        # P2 修复（契约 `GS-A07`）：**不**回退 `ainvoke` —— 那会把整张图重跑一遍，
        # 节点副作用（LLM 调用 / DB 写入）与成本翻倍，代价远高于一次显式异常。
        # 本项目不使用 LangGraph 中断（无 `interrupt` / checkpointer），正常图必然
        # 产出顶层 `values` 快照；走到这里说明图被异常中断，应让调用方感知并决定。
        raise RuntimeError(
            "ainvoke_with_events: 图未产出顶层 values 快照（疑似被中断），"
            f"拒绝重跑整张图；run_id={emitter.run_id}"
        )

    return final_state
