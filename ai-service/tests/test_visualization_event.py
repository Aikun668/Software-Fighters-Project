"""Tests for app.events.visualization — UI block 校验与 visualization 事件工厂。"""
import json

import pytest

from app.events.types import StreamEventType
from app.events.visualization import parse_ui_block, visualization_event


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


class TestParseUiBlockValid:
    def test_valid_block_returns_normalized_value(self):
        result = parse_ui_block(_valid_block())
        assert result["ok"] is True
        assert result["value"] == {
            "type": "attention_matrix",
            "version": 1,
            "props": {
                "tokenCount": 3,
                "mode": "causal",
                "queryLabels": ["我", "爱", "NLP"],
                "keyLabels": ["我", "爱", "NLP"],
            },
        }

    def test_labels_are_copies_not_references(self):
        block = _valid_block()
        result = parse_ui_block(block)
        assert result["ok"] is True
        props = result["value"]["props"]
        assert props["queryLabels"] == block["props"]["queryLabels"]
        assert props["queryLabels"] is not block["props"]["queryLabels"]
        assert props["keyLabels"] is not block["props"]["keyLabels"]

    def test_optional_labels_can_be_omitted(self):
        result = parse_ui_block({
            "type": "attention_matrix",
            "version": 1,
            "props": {"tokenCount": 4, "mode": "bidirectional"},
        })
        assert result["ok"] is True
        assert result["value"]["props"] == {"tokenCount": 4, "mode": "bidirectional"}

    def test_boundary_token_counts_accepted(self):
        for count in (3, 8):
            result = parse_ui_block({
                "type": "attention_matrix",
                "version": 1,
                "props": {"tokenCount": count, "mode": "causal"},
            })
            assert result["ok"] is True


class TestParseUiBlockEnvelopeRejections:
    @pytest.mark.parametrize("bad", [None, [1, 2, 3], "block", 42])
    def test_non_object_inputs_rejected(self, bad):
        result = parse_ui_block(bad)
        assert result["ok"] is False
        assert result["error"]

    def test_missing_props_rejected(self):
        result = parse_ui_block({"type": "attention_matrix", "version": 1})
        assert result["ok"] is False
        assert "props" in result["error"]

    def test_unknown_envelope_key_rejected(self):
        block = _valid_block()
        block["extra"] = "oops"
        result = parse_ui_block(block)
        assert result["ok"] is False
        assert "extra" in result["error"]

    @pytest.mark.parametrize("bad_version", [5.5, "1", True, None])
    def test_non_integer_version_rejected(self, bad_version):
        result = parse_ui_block({
            "type": "attention_matrix",
            "version": bad_version,
            "props": {"tokenCount": 3, "mode": "causal"},
        })
        assert result["ok"] is False
        assert "version" in result["error"]

    def test_unsupported_type_rejected(self):
        result = parse_ui_block({
            "type": "other_chart",
            "version": 1,
            "props": {"tokenCount": 3, "mode": "causal"},
        })
        assert result["ok"] is False

    def test_unsupported_version_rejected(self):
        result = parse_ui_block({
            "type": "attention_matrix",
            "version": 2,
            "props": {"tokenCount": 3, "mode": "causal"},
        })
        assert result["ok"] is False


class TestParseUiBlockPropsRejections:
    def test_weights_rejected_with_d007(self):
        block = _valid_block()
        block["props"]["weights"] = [[0.1, 0.2, 0.7]]
        result = parse_ui_block(block)
        assert result["ok"] is False
        assert "weights" in result["error"]

    @pytest.mark.parametrize("bad_count", [2, 9, 5.5, "5", True, None])
    def test_bad_token_count_rejected(self, bad_count):
        result = parse_ui_block({
            "type": "attention_matrix",
            "version": 1,
            "props": {"tokenCount": bad_count, "mode": "causal"},
        })
        assert result["ok"] is False
        assert "tokenCount" in result["error"]

    def test_bad_mode_rejected(self):
        result = parse_ui_block({
            "type": "attention_matrix",
            "version": 1,
            "props": {"tokenCount": 3, "mode": "full"},
        })
        assert result["ok"] is False
        assert "mode" in result["error"]

    def test_labels_length_mismatch_rejected(self):
        result = parse_ui_block({
            "type": "attention_matrix",
            "version": 1,
            "props": {
                "tokenCount": 3,
                "mode": "causal",
                "queryLabels": ["a", "b"],
            },
        })
        assert result["ok"] is False
        assert "queryLabels" in result["error"]

    def test_labels_not_string_array_rejected(self):
        result = parse_ui_block({
            "type": "attention_matrix",
            "version": 1,
            "props": {
                "tokenCount": 3,
                "mode": "causal",
                "keyLabels": ["a", 2, "c"],
            },
        })
        assert result["ok"] is False
        assert "keyLabels" in result["error"]

    def test_null_labels_rejected(self):
        # 与前端一致：labels 提供了但为 null → 必须是字符串数组
        result = parse_ui_block({
            "type": "attention_matrix",
            "version": 1,
            "props": {"tokenCount": 3, "mode": "causal", "queryLabels": None},
        })
        assert result["ok"] is False
        assert "queryLabels" in result["error"]

    def test_unknown_props_key_rejected(self):
        result = parse_ui_block({
            "type": "attention_matrix",
            "version": 1,
            "props": {"tokenCount": 3, "mode": "causal", "color": "red"},
        })
        assert result["ok"] is False
        assert "color" in result["error"]


class TestParseConvWindow:
    """conv_window v1：CNN/卷积/特征图等滑窗概念的网格可视化（D-014）。"""

    def _conv_block(self, **overrides) -> dict:
        props = {"inputRows": 5, "inputCols": 5, "kernelSize": 3}
        props.update(overrides)
        return {"type": "conv_window", "version": 1, "props": props}

    def test_valid_conv_normalized_with_default_stride(self):
        result = parse_ui_block(self._conv_block())
        assert result["ok"] is True
        assert result["value"]["props"] == {
            "inputRows": 5, "inputCols": 5, "kernelSize": 3, "stride": 1,
        }

    def test_valid_conv_with_stride_2(self):
        result = parse_ui_block(self._conv_block(stride=2))
        assert result["ok"] is True
        assert result["value"]["props"]["stride"] == 2

    def test_boundary_dims_accepted(self):
        assert parse_ui_block(self._conv_block(inputRows=3, inputCols=8, kernelSize=2))["ok"] is True
        assert parse_ui_block(self._conv_block(inputRows=8, inputCols=8, kernelSize=5))["ok"] is True

    @pytest.mark.parametrize(
        "overrides",
        [
            {"inputRows": 2}, {"inputRows": 9}, {"inputCols": 2}, {"inputCols": 9},
            {"kernelSize": 1}, {"kernelSize": 6}, {"stride": 0}, {"stride": 3},
            {"inputRows": 5.5}, {"kernelSize": "3"}, {"stride": None},
        ],
    )
    def test_bad_dims_rejected(self, overrides):
        result = parse_ui_block(self._conv_block(**overrides))
        assert result["ok"] is False
        assert result["error"]

    def test_kernel_larger_than_input_rejected(self):
        result = parse_ui_block(self._conv_block(inputRows=3, inputCols=8, kernelSize=4))
        assert result["ok"] is False
        assert "kernelSize" in result["error"]

    def test_unknown_conv_prop_rejected(self):
        result = parse_ui_block(self._conv_block(featureMap=[[1]]))
        assert result["ok"] is False
        assert "featureMap" in result["error"]

    def test_conv_event_sse_shape(self):
        event = visualization_event(self._conv_block(stride=2))
        assert event.type is StreamEventType.VISUALIZATION
        payload = json.loads(event.to_sse().removeprefix("data: "))
        assert payload["type"] == "visualization"
        assert payload["data"] == {
            "type": "conv_window",
            "version": 1,
            "props": {"inputRows": 5, "inputCols": 5, "kernelSize": 3, "stride": 2},
        }


class TestVisualizationEvent:
    def test_event_type_and_sse_shape(self):
        event = visualization_event(_valid_block())
        assert event.type is StreamEventType.VISUALIZATION

        sse = event.to_sse()
        assert sse.startswith("data: ")
        assert sse.endswith("\n\n")

        payload = json.loads(sse.removeprefix("data: "))
        assert payload["type"] == "visualization"
        assert payload["data"] == {
            "type": "attention_matrix",
            "version": 1,
            "props": {
                "tokenCount": 3,
                "mode": "causal",
                "queryLabels": ["我", "爱", "NLP"],
                "keyLabels": ["我", "爱", "NLP"],
            },
        }

    def test_event_data_is_normalized_copy(self):
        block = _valid_block()
        event = visualization_event(block)
        assert event.data["props"]["queryLabels"] is not block["props"]["queryLabels"]
        assert event.data["props"]["keyLabels"] is not block["props"]["keyLabels"]

    def test_invalid_block_raises_value_error(self):
        block = {
            "type": "attention_matrix",
            "version": 1,
            "props": {"tokenCount": 3, "mode": "causal", "weights": []},
        }
        with pytest.raises(ValueError) as exc_info:
            visualization_event(block)
        assert "weights" in str(exc_info.value)
