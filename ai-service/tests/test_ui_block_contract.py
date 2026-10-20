"""双端契约测试：ui-block 校验结论必须与前端一致（D-014）。

fixtures 见 tests/fixtures/ui_block_contract.json——同一批 block 由
本测试（后端 parse_ui_block）与前端 contract.spec.ts（dispatchUiBlock）
各跑一遍，只比对 ok 布尔结论（error 文案允许各端自述）。新增 block
类型时在 fixtures 追加用例，双端测试自动参数化，防止手写镜像漂移。
"""

import json
from pathlib import Path

import pytest

from app.events.visualization import parse_ui_block

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ui_block_contract.json"
_FIXTURES = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))["fixtures"]


@pytest.mark.parametrize(
    "case",
    _FIXTURES,
    ids=[case["name"] for case in _FIXTURES],
)
def test_ui_block_contract(case: dict) -> None:
    result = parse_ui_block(case["block"])
    assert result["ok"] is case["ok"], (
        f'{case["name"]}: 期望 ok={case["ok"]}，后端返回 {result}'
    )


def test_fixture_file_covers_both_registered_types() -> None:
    """契约文件必须同时覆盖已注册的每一种类型（防止只测旧类型）。"""
    names = {case["block"].get("type") for case in _FIXTURES if isinstance(case["block"], dict)}
    assert "attention_matrix" in names
    assert "conv_window" in names
