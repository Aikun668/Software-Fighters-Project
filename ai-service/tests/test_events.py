"""Tests for app.events.types — StreamEvent serialization."""
import pytest
from app.events.types import (
    StreamEventType, StreamEvent,
    stage_start, stage_end, progress_event, error_event, done_event,
)


class TestStreamEventType:
    def test_all_values_are_strings(self):
        for member in StreamEventType:
            assert isinstance(member.value, str)

    def test_expected_types_exist(self):
        names = {m.name for m in StreamEventType}
        assert "STAGE_START" in names
        assert "STAGE_END" in names
        assert "PROGRESS" in names
        assert "ERROR" in names
        assert "DONE" in names


class TestStreamEvent:
    def test_to_sse_format(self):
        event = stage_start("plan", "正在规划大纲...", 0.1)
        sse = event.to_sse()
        assert sse.startswith("data: ")
        assert sse.endswith("\n\n")
        assert '"type"' in sse
        assert '"stage"' in sse
        assert '"message"' in sse
        assert '"progress"' in sse

    def test_to_sse_omits_empty_fields(self):
        event = done_event()
        sse = event.to_sse()
        assert "stage" not in sse
        assert "message" not in sse
        assert "progress" not in sse

    def test_factory_functions(self):
        assert stage_start("plan", "test").type == StreamEventType.STAGE_START
        assert stage_end("plan", "done").type == StreamEventType.STAGE_END
        assert progress_event("gen", "doing", 0.5).type == StreamEventType.PROGRESS
        assert error_event("gen", "fail").type == StreamEventType.ERROR
        assert done_event().type == StreamEventType.DONE

    def test_progress_rounding(self):
        event = progress_event("gen", "test", 0.12345)
        sse = event.to_sse()
        assert "0.12" in sse
