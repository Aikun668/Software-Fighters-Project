"""visualization SSE 事件：结构化 UI block 校验与事件工厂。

约束镜像前端 frontend/src/components/chat/ui-blocks/schema.ts（手写校验，
不引入第三方依赖）。AI 输出的 props 不得包含 weights（D-007）；block 作为
独立 visualization 事件下发，正文仍是 Markdown（D-004，方案 A / D-010）。
"""

from typing import Any

from app.events.types import StreamEvent, StreamEventType

ATTENTION_MODES = ("causal", "bidirectional")
ATTENTION_TOKEN_MIN = 3
ATTENTION_TOKEN_MAX = 8

ENVELOPE_KEYS = ("type", "version", "props")
ATTENTION_PROP_KEYS = ("tokenCount", "mode", "queryLabels", "keyLabels")


def _error(message: str) -> dict[str, Any]:
    return {"ok": False, "error": message}


def _is_plain_object(value: Any) -> bool:
    return isinstance(value, dict)


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _find_unknown_key(obj: dict, allowed: tuple[str, ...]) -> str | None:
    for key in obj:
        if key not in allowed:
            return key
    return None


def _is_int(value: Any) -> bool:
    # JSON 的 true/false 反序列化为 bool，是 int 的子类，需显式排除
    return isinstance(value, int) and not isinstance(value, bool)


def parse_ui_block(input: Any) -> dict[str, Any]:
    """校验 UI block，本轮只支持 attention_matrix v1。

    返回结构参照前端 schema.ts：通过返回 {"ok": True, "value": 规范化副本}
    （labels 为复制的新数组，不引用原输入）；失败返回
    {"ok": False, "error": 可读错误}，不抛异常。
    """
    # ── 外层 envelope：只允许 {type, version, props} ──
    if not _is_plain_object(input):
        return _error("UI block 必须是对象")
    unknown = _find_unknown_key(input, ENVELOPE_KEYS)
    if unknown is not None:
        return _error(f'UI block 含有未知字段 "{unknown}"')
    block_type = input.get("type")
    if not isinstance(block_type, str) or not block_type:
        return _error("type 必须是非空字符串")
    version = input.get("version")
    if not _is_int(version):
        return _error(f"version 必须是整数，当前为 {version!r}")
    if "props" not in input:
        return _error("缺少 props")

    # ── 类型分发：目前只注册了 attention_matrix v1 ──
    if block_type != "attention_matrix":
        return _error(f'不支持的 UI block 类型 "{block_type}"')
    if version != 1:
        return _error(f"不支持的 attention_matrix 版本 {version}")

    # ── attention_matrix v1 props（镜像前端 validateAttentionMatrixProps）──
    props = input["props"]
    if not _is_plain_object(props):
        return _error("attention_matrix 的 props 必须是对象")
    if "weights" in props:
        return _error("props 不允许包含 weights：AI 输出不得提供真实注意力权重（D-007）")
    unknown_prop = _find_unknown_key(props, ATTENTION_PROP_KEYS)
    if unknown_prop is not None:
        return _error(f'props 含有未知字段 "{unknown_prop}"')

    token_count = props.get("tokenCount")
    if not _is_int(token_count) or not (
        ATTENTION_TOKEN_MIN <= token_count <= ATTENTION_TOKEN_MAX
    ):
        return _error(
            f"tokenCount 必须是 {ATTENTION_TOKEN_MIN}..{ATTENTION_TOKEN_MAX} 之间的整数，"
            f"当前为 {token_count!r}"
        )
    mode = props.get("mode")
    if mode not in ATTENTION_MODES:
        return _error(f"mode 必须是 causal 或 bidirectional，当前为 {mode!r}")

    normalized_props: dict[str, Any] = {"tokenCount": token_count, "mode": mode}
    for name in ("queryLabels", "keyLabels"):
        if name not in props:
            continue
        labels = props[name]
        if not _is_string_list(labels):
            return _error(f"{name} 必须是字符串数组")
        if len(labels) != token_count:
            return _error(
                f"{name} 长度必须等于 tokenCount ({token_count})，当前为 {len(labels)}"
            )
        normalized_props[name] = list(labels)  # 复制副本，不返回原引用

    return {
        "ok": True,
        "value": {"type": block_type, "version": version, "props": normalized_props},
    }


def visualization_event(block: Any) -> StreamEvent:
    """构造 visualization SSE 事件（方案 A：block 独立下发，D-004/D-010）。

    先经 parse_ui_block 校验：未通过时抛 ValueError —— 语义是调用方传入了
    不符合协议的 block（上游 bug 或 LLM 输出未被正确约束），应快速失败暴露，
    异常信息携带校验器的可读错误；通过时返回
    StreamEvent(type=StreamEventType.VISUALIZATION, data=规范化后的 block 副本)，
    其 to_sse() 输出形状为 {"type": "visualization", "data": {type, version, props}}。
    """
    result = parse_ui_block(block)
    if not result["ok"]:
        raise ValueError(f"非法 visualization UI block：{result['error']}")
    return StreamEvent(type=StreamEventType.VISUALIZATION, data=result["value"])
