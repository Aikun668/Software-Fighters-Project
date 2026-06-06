import asyncio
import json
import pytest
from unittest.mock import patch, AsyncMock

from app.services.llm_service import SparkLLM


class TestSparkLLMMock:
    def test_mock_mode_no_credentials_needed(self):
        llm = SparkLLM(use_mock=True)
        assert llm.use_mock is True

    def test_real_mode_requires_credentials(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError):
                SparkLLM(use_mock=False)

    @pytest.mark.asyncio
    async def test_mock_chat_response(self):
        llm = SparkLLM(use_mock=True)
        messages = [{"role": "user", "content": "Hello"}]
        response = await llm.chat(messages)
        assert isinstance(response, str)
        assert len(response) > 0

    @pytest.mark.asyncio
    async def test_mock_chat_stream(self):
        llm = SparkLLM(use_mock=True)
        messages = [{"role": "user", "content": "Hello"}]
        chunks = []
        async for chunk in llm.chat_stream(messages):
            chunks.append(chunk)
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_mock_chat_with_system_prompt(self):
        llm = SparkLLM(use_mock=True)
        messages = [{"role": "user", "content": "Test"}]
        response = await llm.chat(messages, system_prompt="You are a test assistant.")
        assert isinstance(response, str)


class TestSparkLLMWebSocket:
    @pytest.fixture
    def mock_ws(self):
        ws = AsyncMock()
        ws.send = AsyncMock()
        
        class MockAsyncIterator:
            def __init__(self, items):
                self.items = items
                self.index = 0
            
            def __aiter__(self):
                return self
            
            async def __anext__(self):
                if self.index >= len(self.items):
                    raise StopAsyncIteration
                item = self.items[self.index]
                self.index += 1
                return item
        
        ws.__aiter__ = lambda self: MockAsyncIterator([
            json.dumps({
                "header": {"code": 0, "status": 0},
                "payload": {"choices": {"text": [{"content": "Hello"}]}}
            }),
            json.dumps({
                "header": {"code": 0, "status": 2},
                "payload": {"choices": {"text": [{"content": " World"}]}}
            }),
        ])
        return ws

    @pytest.mark.asyncio
    async def test_chat_websocket_success(self, mock_ws):
        with patch.dict("os.environ", {
            "SPARK_APP_ID": "test_id",
            "SPARK_API_KEY": "test_key",
            "SPARK_API_SECRET": "test_secret",
        }):
            with patch("websockets.connect", return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_ws),
                __aexit__=AsyncMock(return_value=False)
            )):
                llm = SparkLLM(use_mock=False)
                messages = [{"role": "user", "content": "Hello"}]
                response = await llm.chat(messages)
                assert "Hello World" in response

    @pytest.mark.asyncio
    async def test_chat_websocket_error_code(self):
        error_msg = json.dumps({
            "header": {"code": 10001, "message": "Authentication failed"},
        })
        mock_ws = AsyncMock()
        
        class MockAsyncIterator:
            def __init__(self, items):
                self.items = items
                self.index = 0
            def __aiter__(self):
                return self
            async def __anext__(self):
                if self.index >= len(self.items):
                    raise StopAsyncIteration
                item = self.items[self.index]
                self.index += 1
                return item
        
        mock_ws.__aiter__ = lambda self: MockAsyncIterator([error_msg])

        with patch.dict("os.environ", {
            "SPARK_APP_ID": "test_id",
            "SPARK_API_KEY": "test_key",
            "SPARK_API_SECRET": "test_secret",
        }):
            with patch("websockets.connect", return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_ws),
                __aexit__=AsyncMock(return_value=False)
            )):
                llm = SparkLLM(use_mock=False)
                messages = [{"role": "user", "content": "Hello"}]
                with pytest.raises(RuntimeError) as exc_info:
                    await llm.chat(messages)
                assert "Spark WebSocket error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_chat_timeout(self):
        with patch.dict("os.environ", {
            "SPARK_APP_ID": "test_id",
            "SPARK_API_KEY": "test_key",
            "SPARK_API_SECRET": "test_secret",
        }):
            with patch("websockets.connect", side_effect=asyncio.TimeoutError()):
                llm = SparkLLM(use_mock=False)
                messages = [{"role": "user", "content": "Hello"}]
                with pytest.raises(RuntimeError) as exc_info:
                    await llm.chat(messages)
                assert "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_chat_os_error(self):
        with patch.dict("os.environ", {
            "SPARK_APP_ID": "test_id",
            "SPARK_API_KEY": "test_key",
            "SPARK_API_SECRET": "test_secret",
        }):
            with patch("websockets.connect", side_effect=OSError("Connection refused")):
                llm = SparkLLM(use_mock=False)
                messages = [{"role": "user", "content": "Hello"}]
                with pytest.raises(RuntimeError) as exc_info:
                    await llm.chat(messages)
                assert "failed" in str(exc_info.value).lower()


class TestSparkLLMUrl:
    def test_build_ws_url(self):
        with patch.dict("os.environ", {
            "SPARK_APP_ID": "test_id",
            "SPARK_API_KEY": "test_key",
            "SPARK_API_SECRET": "test_secret",
        }):
            llm = SparkLLM(use_mock=False)
            url = llm._build_ws_url()
            assert url.startswith("wss://")
            assert "spark-api" in url
            assert "authorization=" in url
