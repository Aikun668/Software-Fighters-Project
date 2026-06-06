"""Tests for structured error code system."""
import json

import pytest

from app.api.errors import ErrorCode, api_error, api_success


def _body(resp) -> dict:
    return json.loads(resp.body)


class TestErrorCode:
    def test_all_codes_are_unique(self):
        values = [e.value for e in ErrorCode]
        assert len(values) == len(set(values))

    def test_codes_are_strings(self):
        for e in ErrorCode:
            assert isinstance(e.value, str)
            assert isinstance(e, str)

    def test_expected_codes_exist(self):
        expected = {
            "MISSING_REQUIRED_FIELD",
            "INVALID_REQUEST",
            "UPSTREAM_ERROR",
            "GENERATION_FAILED",
            "PERSIST_FAILED",
            "PARSE_FAILED",
            "CONTENT_UNSAFE",
            "AGENT_TIMEOUT",
            "NOT_FOUND",
            "INTERNAL_ERROR",
        }
        actual = {e.value for e in ErrorCode}
        assert actual == expected


class TestApiError:
    def test_minimal_response(self):
        resp = api_error(ErrorCode.INVALID_REQUEST, "bad input")
        body = _body(resp)
        assert body["success"] is False
        assert body["errorCode"] == "INVALID_REQUEST"
        assert body["error"] == "bad input"
        assert resp.status_code == 400

    def test_with_details(self):
        resp = api_error(
            ErrorCode.UPSTREAM_ERROR,
            "LLM failed",
            details={"provider": "spark", "retry": 3},
        )
        body = _body(resp)
        assert body["details"] == {"provider": "spark", "retry": 3}

    def test_custom_status_code(self):
        resp = api_error(
            ErrorCode.NOT_FOUND, "gone", status_code=404
        )
        assert resp.status_code == 404

    def test_server_error_status(self):
        resp = api_error(
            ErrorCode.INTERNAL_ERROR, "boom", status_code=500
        )
        assert resp.status_code == 500


class TestApiSuccess:
    def test_empty_success(self):
        resp = api_success()
        body = _body(resp)
        assert body == {"success": True}
        assert resp.status_code == 200

    def test_with_data(self):
        resp = api_success({"key": "value"})
        body = _body(resp)
        assert body["success"] is True
        assert body["data"] == {"key": "value"}

    def test_custom_status_code(self):
        resp = api_success({"id": 1}, status_code=201)
        assert resp.status_code == 201

    def test_list_data(self):
        resp = api_success([1, 2, 3])
        body = _body(resp)
        assert body["data"] == [1, 2, 3]
