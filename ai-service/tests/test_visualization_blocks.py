"""Tests for app.services.visualization_blocks — ui-block 围栏抽取（T006）。

覆盖任务单验收场景：无围栏原样返回 / 合法围栏抽取剥离 / 多个围栏 /
JSON 非法保留 / 含 weights 保留（D-007）/ 普通代码块不受影响，
以及 ChatTaskDispatcher 接线（合法 block → visualization 事件随正文之后下发）。
"""
import json

import pytest

from app.events.types import StreamEventType
from app.services.visualization_blocks import (
    extract_ui_blocks,
    extract_ui_blocks_from_payload,
)


def _valid_block() -> dict:
    return {
        "type": "attention_matrix",
        "version": 1,
        "props": {
            "tokenCount": 3,
            "mode": "causal",
            "queryLabels": ["我", "爱", "NLP"],
            "keyLabels": ["我", "爱", "NLP"],
        },
    }


def _fence(body: str) -> str:
    """构造 ```ui-block 围栏，body 为围栏内原文。"""
    return f"```ui-block\n{body}\n```"


def _fenced_block(block: dict) -> str:
    return _fence(json.dumps(block, ensure_ascii=False))


class TestExtractUiBlocksNoFence:
    def test_plain_text_unchanged(self):
        text = "注意力机制是 Transformer 的核心。\n\n它分为 causal 与 bidirectional 两种。"
        cleaned, blocks = extract_ui_blocks(text)
        assert cleaned == text
        assert blocks == []

    def test_empty_string(self):
        assert extract_ui_blocks("") == ("", [])

    def test_normal_code_blocks_untouched(self):
        """普通代码块（其他 info string / 无 info string）一概不动。"""
        text = (
            "示例如下：\n\n"
            "```python\nprint('hello')\n```\n\n"
            "```\nplain fence\n```\n\n"
            "```json\n{\"a\": 1}\n```\n"
        )
        cleaned, blocks = extract_ui_blocks(text)
        assert cleaned == text
        assert blocks == []

    def test_case_sensitive_info_string(self):
        """info string 大小写敏感：```UI-BLOCK 不是 ui-block 围栏。"""
        text = _fence(json.dumps(_valid_block())).replace("ui-block", "UI-BLOCK")
        cleaned, blocks = extract_ui_blocks(text)
        assert cleaned == text
        assert blocks == []


class TestExtractUiBlocksValid:
    def test_valid_fence_extracted_and_stripped(self):
        text = (
            "注意力机制可以用矩阵表示：\n\n"
            + _fenced_block(_valid_block())
            + "\n\n如上所示。"
        )
        cleaned, blocks = extract_ui_blocks(text)
        assert "ui-block" not in cleaned
        assert "attention_matrix" not in cleaned
        assert cleaned.startswith("注意力机制可以用矩阵表示：")
        assert cleaned.endswith("如上所示。")
        assert len(blocks) == 1
        assert blocks[0] == {
            "type": "attention_matrix",
            "version": 1,
            "props": {
                "tokenCount": 3,
                "mode": "causal",
                "queryLabels": ["我", "爱", "NLP"],
                "keyLabels": ["我", "爱", "NLP"],
            },
        }

    def test_fence_at_start_and_end(self):
        cleaned, blocks = extract_ui_blocks(
            _fenced_block(_valid_block()) + "\n结尾正文。"
        )
        assert cleaned == "结尾正文。"
        assert len(blocks) == 1

        cleaned, blocks = extract_ui_blocks(
            "开头正文。\n" + _fenced_block(_valid_block())
        )
        assert cleaned == "开头正文。\n"
        assert len(blocks) == 1

    def test_fence_only_text_becomes_empty(self):
        cleaned, blocks = extract_ui_blocks(_fenced_block(_valid_block()))
        assert cleaned == ""
        assert len(blocks) == 1

    def test_multiple_fences_all_extracted_in_order(self):
        second = {
            "type": "attention_matrix",
            "version": 1,
            "props": {"tokenCount": 4, "mode": "bidirectional"},
        }
        text = (
            "第一段。\n\n"
            + _fenced_block(_valid_block())
            + "\n\n中间正文。\n\n"
            + _fenced_block(second)
            + "\n\n收尾。"
        )
        cleaned, blocks = extract_ui_blocks(text)
        assert len(blocks) == 2
        assert blocks[0]["props"]["mode"] == "causal"
        assert blocks[1]["props"]["tokenCount"] == 4
        assert cleaned == "第一段。\n\n中间正文。\n\n收尾。"

    def test_valid_fence_mixed_with_normal_code_block(self):
        text = (
            "先看代码：\n\n```python\nprint(1)\n```\n\n"
            "再看图：\n\n" + _fenced_block(_valid_block()) + "\n\n完。"
        )
        cleaned, blocks = extract_ui_blocks(text)
        assert "```python\nprint(1)\n```" in cleaned
        assert len(blocks) == 1


class TestExtractUiBlocksInvalid:
    def test_invalid_json_fence_kept(self):
        text = "正文前。\n\n" + _fence("{not json") + "\n\n正文后。"
        cleaned, blocks = extract_ui_blocks(text)
        assert cleaned == text, "JSON 非法的围栏必须原样保留（失败不吞正文）"
        assert blocks == []

    def test_weights_fence_kept_d007(self):
        block = _valid_block()
        block["props"]["weights"] = [[0.1, 0.2, 0.7]]
        text = "说明。\n\n" + _fenced_block(block)
        cleaned, blocks = extract_ui_blocks(text)
        assert "weights" in cleaned
        assert "ui-block" in cleaned
        assert blocks == []

    def test_json_object_but_schema_invalid_kept(self):
        block = {"type": "other_chart", "version": 1, "props": {}}
        text = _fenced_block(block)
        cleaned, blocks = extract_ui_blocks(text)
        assert cleaned == text
        assert blocks == []

    def test_json_non_object_kept(self):
        text = _fence("[1, 2, 3]")
        cleaned, blocks = extract_ui_blocks(text)
        assert cleaned == text
        assert blocks == []

    def test_unclosed_fence_kept(self):
        text = "```ui-block\n{\"type\": \"attention_matrix\"}"
        cleaned, blocks = extract_ui_blocks(text)
        assert cleaned == text
        assert blocks == []

    def test_valid_and_invalid_fences_mixed(self):
        """合法的剥离、非法的保留，互不影响。"""
        bad = _fence("{oops")
        text = "前。\n\n" + _fenced_block(_valid_block()) + "\n\n" + bad + "\n\n后。"
        cleaned, blocks = extract_ui_blocks(text)
        assert len(blocks) == 1
        assert bad in cleaned
        assert "attention_matrix" not in cleaned


class TestExtractUiBlocksFromPayload:
    def test_same_text_in_response_and_content_extracted_once(self):
        """solution/summary 合成路径双键同值：只抽取一次，两键同步替换。"""
        fenced = "正文。\n\n" + _fenced_block(_valid_block()) + "\n\n收尾。"
        payload = {"response": fenced, "content": fenced, "stage": "auto"}
        blocks = extract_ui_blocks_from_payload(payload)
        assert len(blocks) == 1
        assert payload["response"] == "正文。\n\n收尾。"
        assert payload["content"] == "正文。\n\n收尾。"
        assert payload["stage"] == "auto"

    def test_different_texts_extracted_separately(self):
        payload = {
            "response": "A。\n\n" + _fenced_block(_valid_block()) + "\n\n收A。",
            "content": "B。\n\n" + _fenced_block(_valid_block()) + "\n\n收B。",
        }
        blocks = extract_ui_blocks_from_payload(payload)
        assert len(blocks) == 2
        assert payload["response"] == "A。\n\n收A。"
        assert payload["content"] == "B。\n\n收B。"

    def test_payload_without_text_keys_untouched(self):
        payload = {"type": "plan", "steps": [{"title": "x"}]}
        assert extract_ui_blocks_from_payload(payload) == []
        assert payload == {"type": "plan", "steps": [{"title": "x"}]}


class TestDispatcherWiring:
    """ChatTaskDispatcher 接线：最终正文抽取 + visualization 事件随正文之后下发。"""

    @staticmethod
    async def _run(payload_response: str):
        from app.centers.chat_task_dispatcher import ChatTaskDispatcher
        from app.centers.schemas import CenterResult, CenterTask, ExecutionPlan

        class FakeAutoCenter:
            async def execute(self, task, on_token=None):
                if on_token is not None:
                    await on_token("正文前段")
                return CenterResult(
                    mode="auto",
                    intent="tutor_question",
                    event_type="content",
                    payload={"response": payload_response},
                    agent="TutorAgent",
                    sequence=0,
                )

        plan = ExecutionPlan(
            tasks=[CenterTask(mode="auto", intent="tutor_question", input="什么是注意力？")],
        )
        events = []
        async for event in ChatTaskDispatcher(auto_center=FakeAutoCenter()).execute(plan):
            events.append(event)
        return events

    @pytest.mark.asyncio
    async def test_valid_block_yields_visualization_after_content(self):
        events = await self._run(
            "注意力机制如下：\n\n" + _fenced_block(_valid_block()) + "\n\n详见上文。"
        )
        types = [e.type.value for e in events]

        content = next(e for e in events if e.type.value == "content")
        assert "ui-block" not in content.data["response"]
        assert content.data["response"] == "注意力机制如下：\n\n详见上文。"
        assert content.data.get("partial") is True  # 发过 token，收尾帧带 partial

        assert "visualization" in types, f"合法 block 必须产生 visualization 事件: {types}"
        assert types.index("visualization") > types.index("content")
        assert types[-1] == "done", "done 必须仍是最后一个事件"

        viz = next(e for e in events if e.type.value == "visualization")
        assert viz.type is StreamEventType.VISUALIZATION
        assert viz.data["type"] == "attention_matrix"
        assert viz.data["props"]["tokenCount"] == 3

    @pytest.mark.asyncio
    async def test_invalid_block_keeps_text_and_no_visualization_event(self):
        fenced = "说明。\n\n" + _fence("{not json")
        events = await self._run(fenced)
        types = [e.type.value for e in events]

        content = next(e for e in events if e.type.value == "content")
        assert content.data["response"] == fenced, "非法围栏正文必须原样下发"
        assert "visualization" not in types

    @pytest.mark.asyncio
    async def test_no_fence_no_visualization_event(self):
        events = await self._run("普通回答，没有任何围栏。")
        types = [e.type.value for e in events]
        content = next(e for e in events if e.type.value == "content")
        assert content.data["response"] == "普通回答，没有任何围栏。"
        assert "visualization" not in types
        assert types[-1] == "done"
