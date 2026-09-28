import pytest
from unittest.mock import patch

from app.services.llm_service import OpenAILLM


class _FakeStreamContent:
    def __init__(self, lines):
        self._lines = [line.encode("utf-8") for line in lines]

    async def readline(self):
        if not self._lines:
            return b""
        return self._lines.pop(0)


class _FakeHttpResponse:
    status = 200

    def __init__(self, lines):
        self.content = _FakeStreamContent(lines)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def text(self):
        return ""


class _FakeHttpSession:
    def __init__(self, responses, requests):
        self._responses = responses
        self._requests = requests

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def post(self, url, *, json, headers):
        self._requests.append(json)
        response = self._responses.pop(0)
        return response if isinstance(response, _FakeHttpResponse) else _FakeHttpResponse(response)


class TestOpenAIThinkingMode:
    @pytest.mark.asyncio
    async def test_empty_non_stream_final_retries_with_thinking_disabled(self):
        requests = []
        responses = []
        for content in ("", "降级后的最终答案"):
            response = _FakeHttpResponse([])

            async def fake_json(content=content):
                return {"choices": [{"message": {"content": content}}]}

            response.json = fake_json
            responses.append(response)
        session_factory = lambda: _FakeHttpSession(responses, requests)

        with patch("app.services.llm_service._create_session", side_effect=session_factory):
            llm = OpenAILLM(
                api_key="test-key",
                base_url="https://example.test/v1",
                model="deepseek-v4-flash",
                thinking_enabled=True,
            )
            result = await llm.chat([{"role": "user", "content": "解释进程"}])

        assert result == "降级后的最终答案"
        assert [request["thinking"]["type"] for request in requests] == ["enabled", "disabled"]

    @pytest.mark.asyncio
    async def test_empty_final_after_reasoning_retries_with_thinking_disabled(self):
        requests = []
        responses = [
            [
                'data: {"choices":[{"delta":{"reasoning_content":"先推理"},"finish_reason":null}]}',
                "data: [DONE]",
            ],
            [
                'data: {"choices":[{"delta":{"content":"最终答案"},"finish_reason":null}]}',
                "data: [DONE]",
            ],
        ]
        session_factory = lambda: _FakeHttpSession(responses, requests)

        with patch("app.services.llm_service._create_session", side_effect=session_factory):
            llm = OpenAILLM(
                api_key="test-key",
                base_url="https://example.test/v1",
                model="deepseek-v4-flash",
                thinking_enabled=True,
            )
            chunks = [chunk async for chunk in llm.chat_stream([{"role": "user", "content": "解释进程"}])]

        assert "".join(chunks) == "最终答案"
        assert [request["thinking"]["type"] for request in requests] == ["enabled", "disabled"]

    @pytest.mark.asyncio
    async def test_chat_sends_explicit_non_thinking_mode_by_default(self):
        requests = []
        response = _FakeHttpResponse([])

        async def fake_json():
            return {"choices": [{"message": {"content": "普通回答"}}]}

        response.json = fake_json
        session_factory = lambda: _FakeHttpSession([response], requests)

        with patch("app.services.llm_service._create_session", side_effect=session_factory):
            llm = OpenAILLM(
                api_key="test-key",
                base_url="https://example.test/v1",
                model="deepseek-v4-flash",
            )
            result = await llm.chat([{"role": "user", "content": "你好"}])

        assert result == "普通回答"
        assert requests[0]["thinking"] == {"type": "disabled"}


