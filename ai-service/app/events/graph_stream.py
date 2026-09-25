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

⚠️ 本层**不改任何传输字节**：只发内部事件，不参与 SSE 帧构造。
`token` / `message.delta` 仍由既有 token 泵负责（见 `app/events/stream.py` 的说明）。
"""

from __future__ import annotations

import logging
from typing import Any

from app.events.stream import ProgressEventType, StreamEmitter

logger = logging.getLogger(__name__)

#: 多模式 + 子图时使用的流模式组合
DEFAULT_STREAM_MODES: tuple[str, ...] = ("updates", "values")


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
    - 订阅者异常被 `StreamEmitter` 隔离，不影响本次执行。

    Args:
        compiled_graph: 已编译的 LangGraph 图（`compile()` 的产物）。
        input_state: 初始状态。
        emitter: 事件源；`None` 表示只要结果、不要事件。
        config: 透传给 LangGraph 的 config（如 `{"recursion_limit": ...}`）。

    Returns:
        终态字典，与 `compiled_graph.ainvoke(input_state)` 逐字段一致。
    """
    if emitter is None:
        return await compiled_graph.ainvoke(input_state, config)

    final_state: dict | None = None
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

    if final_state is None:
        # 兜底：图没有产出顶层 values（例如被中断）→ 回退到 ainvoke，保证返回值语义
        logger.warning(
            "ainvoke_with_events: 未收到顶层 values 快照，回退 ainvoke（run_id=%s）",
            emitter.run_id,
        )
        return await compiled_graph.ainvoke(input_state, config)

    return final_state
