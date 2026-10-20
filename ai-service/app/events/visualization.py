"""visualization SSE 事件：结构化 UI block 校验与事件工厂。

约束镜像前端 frontend/src/components/chat/ui-blocks/schema.ts（手写校验，
不引入第三方依赖）。AI 输出的 props 不得包含 weights（D-007）；block 作为
独立 visualization 事件下发，正文仍是 Markdown（D-004，方案 A / D-010）。

【类型注册表】新增 block 类型只需两步：
1. 写一个 `_parse_xxx_props(props) -> tuple[dict | None, str | None]`
   （返回 (规范化副本, None) 或 (None, 可读错误)）；
2. 在 `_BLOCK_PARSERS` 注册 `"类型名": {版本: 解析函数}`。
前端 registry.ts 同步加条目即可。双端校验结论由同一批契约 fixtures
锁定（tests/fixtures/ui_block_contract.json，后端 test_ui_block_contract.py
与前端 contract.spec.ts 各跑一遍，ok 布尔结论必须一致）。
"""

import logging
from typing import Any, Callable

from app.events.types import StreamEvent, StreamEventType

logger = logging.getLogger(__name__)

# ── attention_matrix v1 ──
ATTENTION_MODES = ("causal", "bidirectional")
ATTENTION_TOKEN_MIN = 3
ATTENTION_TOKEN_MAX = 8
ATTENTION_PROP_KEYS = ("tokenCount", "mode", "queryLabels", "keyLabels")

# ── conv_window v1：网格 + 卷积核滑窗（CNN/卷积/特征图/感受野）──
CONV_ROWS_MIN = 3
CONV_ROWS_MAX = 8
CONV_COLS_MIN = 3
CONV_COLS_MAX = 8
CONV_KERNEL_MIN = 2
CONV_KERNEL_MAX = 5
CONV_STRIDE_MIN = 1
CONV_STRIDE_MAX = 2
CONV_PROP_KEYS = ("inputRows", "inputCols", "kernelSize", "stride")

ENVELOPE_KEYS = ("type", "version", "props")

# props 解析器注册表：{type: {version: parser}}，与前端 registry.ts 一一对应
PropsParser = Callable[[dict], tuple[dict | None, str | None]]
_BLOCK_PARSERS: dict[str, dict[int, PropsParser]] = {}


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


def _parse_attention_props(props: dict) -> tuple[dict | None, str | None]:
    """attention_matrix v1 的 props 校验（镜像前端 validateAttentionMatrixProps）。"""
    if "weights" in props:
        return None, "props 不允许包含 weights：AI 输出不得提供真实注意力权重（D-007）"
    unknown_prop = _find_unknown_key(props, ATTENTION_PROP_KEYS)
    if unknown_prop is not None:
        return None, f'props 含有未知字段 "{unknown_prop}"'

    token_count = props.get("tokenCount")
    if not _is_int(token_count) or not (
        ATTENTION_TOKEN_MIN <= token_count <= ATTENTION_TOKEN_MAX
    ):
        return None, (
            f"tokenCount 必须是 {ATTENTION_TOKEN_MIN}..{ATTENTION_TOKEN_MAX} 之间的整数，"
            f"当前为 {token_count!r}"
        )
    mode = props.get("mode")
    if mode not in ATTENTION_MODES:
        return None, f"mode 必须是 causal 或 bidirectional，当前为 {mode!r}"

    normalized: dict[str, Any] = {"tokenCount": token_count, "mode": mode}
    for name in ("queryLabels", "keyLabels"):
        if name not in props:
            continue
        labels = props[name]
        if not _is_string_list(labels):
            return None, f"{name} 必须是字符串数组"
        if len(labels) != token_count:
            return None, (
                f"{name} 长度必须等于 tokenCount ({token_count})，当前为 {len(labels)}"
            )
        normalized[name] = list(labels)  # 复制副本，不返回原引用
    return normalized, None


def _parse_conv_props(props: dict) -> tuple[dict | None, str | None]:
    """conv_window v1 的 props 校验（镜像前端 validateConvWindowProps）。"""
    unknown_prop = _find_unknown_key(props, CONV_PROP_KEYS)
    if unknown_prop is not None:
        return None, f'props 含有未知字段 "{unknown_prop}"'

    input_rows = props.get("inputRows")
    if not _is_int(input_rows) or not (CONV_ROWS_MIN <= input_rows <= CONV_ROWS_MAX):
        return None, (
            f"inputRows 必须是 {CONV_ROWS_MIN}..{CONV_ROWS_MAX} 之间的整数，"
            f"当前为 {input_rows!r}"
        )
    input_cols = props.get("inputCols")
    if not _is_int(input_cols) or not (CONV_COLS_MIN <= input_cols <= CONV_COLS_MAX):
        return None, (
            f"inputCols 必须是 {CONV_COLS_MIN}..{CONV_COLS_MAX} 之间的整数，"
            f"当前为 {input_cols!r}"
        )
    kernel = props.get("kernelSize")
    if not _is_int(kernel) or not (CONV_KERNEL_MIN <= kernel <= CONV_KERNEL_MAX):
        return None, (
            f"kernelSize 必须是 {CONV_KERNEL_MIN}..{CONV_KERNEL_MAX} 之间的整数，"
            f"当前为 {kernel!r}"
        )
    if kernel > input_rows or kernel > input_cols:
        return None, (
            f"kernelSize ({kernel}) 不得大于输入行数/列数 "
            f"({input_rows}/{input_cols})"
        )
    if "stride" in props:
        stride = props["stride"]
        if not _is_int(stride) or not (CONV_STRIDE_MIN <= stride <= CONV_STRIDE_MAX):
            return None, f"stride 必须是 {CONV_STRIDE_MIN} 或 {CONV_STRIDE_MAX}，当前为 {stride!r}"
    else:
        stride = 1  # 未提供时默认 1（规范化后始终携带）

    return {
        "inputRows": input_rows,
        "inputCols": input_cols,
        "kernelSize": kernel,
        "stride": stride,
    }, None


_BLOCK_PARSERS["attention_matrix"] = {1: _parse_attention_props}
_BLOCK_PARSERS["conv_window"] = {1: _parse_conv_props}


def parse_ui_block(input: Any) -> dict[str, Any]:
    """校验 UI block（envelope + 注册表分发 + 各类型 props 校验）。

    返回结构参照前端 schema.ts：通过返回 {"ok": True, "value": 规范化副本}
    （数组字段为复制的新数组，不引用原输入）；失败返回
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

    # ── 类型分发：按注册表查找 (type, version) 对应的 props 解析器 ──
    versions = _BLOCK_PARSERS.get(block_type)
    if versions is None:
        return _error(f'不支持的 UI block 类型 "{block_type}"')
    parser = versions.get(version)
    if parser is None:
        return _error(f"不支持的 {block_type} 版本 {version}")

    props = input["props"]
    if not _is_plain_object(props):
        return _error(f"{block_type} 的 props 必须是对象")
    normalized, err = parser(props)
    if err is not None:
        return _error(err)

    return {
        "ok": True,
        "value": {"type": block_type, "version": version, "props": normalized},
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
