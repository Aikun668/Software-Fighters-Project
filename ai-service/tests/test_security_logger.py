"""Tests for security logger — structured event logging."""

from unittest.mock import patch

from app.utils.security_logger import SecurityLogger


class TestSecurityLogger:
    def test_log_event_info_level(self):
        with patch("app.utils.security_logger.logger.info") as mock_info:
            SecurityLogger.log_event("hallucination_warning", {"user_id": 1, "agent": "TutorAgent"})
            mock_info.assert_called_once()
            fmt_str, fmt_args = mock_info.call_args[0]
            assert "hallucination_warning" in fmt_args
            assert "user_id=1" in fmt_args
            assert "agent=TutorAgent" in fmt_args

    def test_log_event_warning_level(self):
        with patch("app.utils.security_logger.logger.warning") as mock_warn:
            SecurityLogger.log_event("input_violation", {"user_id": 2})
            mock_warn.assert_called_once()
            fmt_args = mock_warn.call_args[0][1]
            assert "input_violation" in fmt_args

    def test_pipeline_error_uses_warning(self):
        with patch("app.utils.security_logger.logger.warning") as mock_warn:
            SecurityLogger.log_event("pipeline_error", {"user_id": 3})
            mock_warn.assert_called_once()
            fmt_args = mock_warn.call_args[0][1]
            assert "pipeline_error" in fmt_args

    def test_output_flagged_uses_info(self):
        with patch("app.utils.security_logger.logger.info") as mock_info:
            SecurityLogger.log_event("output_flagged", {"user_id": 4})
            mock_info.assert_called_once()
            fmt_args = mock_info.call_args[0][1]
            assert "output_flagged" in fmt_args

    def test_content_preview_truncation(self):
        with patch("app.utils.security_logger.logger.info") as mock_info:
            SecurityLogger.log_event("hallucination_warning", {"content": "x" * 100})
            fmt_args = mock_info.call_args[0][1]
            assert "preview=" in fmt_args
            after_preview = fmt_args.split("preview=")[1]
            preview_val = after_preview.split(" ")[0] if " " in after_preview else after_preview
            assert len(preview_val) <= 50

    def test_empty_content(self):
        with patch("app.utils.security_logger.logger.info") as mock_info:
            SecurityLogger.log_event("hallucination_warning", {"content": ""})
            fmt_args = mock_info.call_args[0][1]
            assert "preview=" in fmt_args

    def test_no_content_field(self):
        with patch("app.utils.security_logger.logger.info") as mock_info:
            SecurityLogger.log_event("hallucination_warning", {})
            fmt_args = mock_info.call_args[0][1]
            assert "preview=" in fmt_args

    def test_default_severity(self):
        with patch("app.utils.security_logger.logger.info") as mock_info:
            SecurityLogger.log_event("output_flagged", {"user_id": 1})
            fmt_args = mock_info.call_args[0][1]
            assert "severity=medium" in fmt_args

    def test_custom_severity(self):
        with patch("app.utils.security_logger.logger.info") as mock_info:
            SecurityLogger.log_event("hallucination_warning", {"user_id": 1}, severity="critical")
            fmt_args = mock_info.call_args[0][1]
            assert "severity=critical" in fmt_args

    def test_extra_field(self):
        with patch("app.utils.security_logger.logger.warning") as mock_warn:
            SecurityLogger.log_event(
                "pipeline_error",
                {"extra": {"component": "SafetyPipeline", "error": "timeout"}},
            )
            mock_warn.assert_called_once()

    def test_all_event_types_logged(self):
        for event_type in ("input_violation", "output_flagged",
                           "hallucination_warning", "pipeline_error"):
            has_called = False
            with patch("app.utils.security_logger.logger.info") as mock_info, \
                 patch("app.utils.security_logger.logger.warning") as mock_warn:
                SecurityLogger.log_event(event_type, {"user_id": 1})
                has_called = mock_info.called or mock_warn.called
            assert has_called, f"event_type {event_type} was not logged"

    def test_all_severity_levels(self):
        for severity in ("low", "medium", "high", "critical"):
            with patch("app.utils.security_logger.logger.info") as mock_info:
                SecurityLogger.log_event(
                    "hallucination_warning", {"user_id": 1}, severity=severity,
                )
                fmt_args = mock_info.call_args[0][1]
                assert f"severity={severity}" in fmt_args
