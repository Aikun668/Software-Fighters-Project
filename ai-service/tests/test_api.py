import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from unittest.mock import MagicMock, patch, AsyncMock

from internal_api import router


def _make_app() -> FastAPI:
    app = FastAPI()

    @app.exception_handler(RequestValidationError)
    async def _handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        msg = errors[0]["msg"] if errors else "请求参数验证失败"
        loc = errors[0].get("loc", [])
        if loc:
            field = str(loc[-1]) if len(loc) > 1 else str(loc[0])
            msg = f"字段 '{field}' {msg}"
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": msg, "error_code": "INVALID_REQUEST"},
        )

    app.include_router(router)
    return app


@pytest.fixture
def client():
    return TestClient(_make_app())


@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=_make_app()), base_url="http://test") as client:
        yield client


class TestInputValidation:
    def test_profile_empty_messages(self, client):
        response = client.post("/internal/profile/chat", json={"user_id": 1})
        assert response.status_code == 400
        assert "messages" in response.json()["error"].lower()

    def test_profile_invalid_messages_type(self, client):
        response = client.post("/internal/profile/chat", json={"user_id": 1, "messages": "not list"})
        assert response.status_code == 400

    def test_resources_empty_topic(self, client):
        response = client.post("/internal/resources/generate", json={"student_id": "1"})
        assert response.status_code == 400
        assert "topic" in response.json()["error"].lower()

    def test_tutor_empty_messages(self, client):
        response = client.post("/internal/tutor/chat", json={"user_id": 1})
        assert response.status_code == 400

    def test_exercise_empty_topic(self, client):
        response = client.post("/internal/exercise/generate", json={"count": 3})
        assert response.status_code == 400

    def test_exercise_count_too_high(self, client):
        response = client.post("/internal/exercise/generate", json={"topic": "Test", "count": 25})
        assert response.status_code == 400

    def test_exercise_count_zero(self, client):
        response = client.post("/internal/exercise/generate", json={"topic": "Test", "count": 0})
        assert response.status_code == 400

    def test_exercise_count_negative(self, client):
        response = client.post("/internal/exercise/generate", json={"topic": "Test", "count": -1})
        assert response.status_code == 400

    def test_exercise_count_string(self, client):
        response = client.post("/internal/exercise/generate", json={"topic": "Test", "count": "three"})
        assert response.status_code == 400


class TestStreamingEndpoints:
    @pytest.mark.asyncio
    async def test_profile_stream(self, async_client):
        with patch("internal_api._get_profile_agent") as mock_get:
            mock_agent = AsyncMock()
            mock_agent.run = AsyncMock(return_value={
                "response": "Hello!",
                "profile_changed": False,
                "current_profile": {},
            })
            mock_get.return_value = mock_agent
            
            response = await async_client.post(
                "/internal/profile/chat",
                json={"user_id": 1, "messages": [{"role": "user", "content": "Hi"}]},
            )
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_resources_stream(self, async_client):
        with patch("internal_api._get_resource_workflow") as mock_get:
            mock_workflow = AsyncMock()
            mock_workflow.run = AsyncMock(return_value={
                "content_blocks": [{"type": "section", "heading": "Test", "content": "Content"}],
                "questions": [],
                "resource_ids": [],
                "response": "Done",
                "error": "",
            })
            mock_get.return_value = mock_workflow

            response = await async_client.post(
                "/internal/resources/generate",
                json={"student_id": "1", "topic": "Python"},
            )
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_tutor_stream(self, async_client):
        with patch("internal_api._get_tutor_agent") as mock_get:
            mock_agent = AsyncMock()
            mock_agent.run = AsyncMock(return_value={"response": "Answer"})
            mock_get.return_value = mock_agent
            
            response = await async_client.post(
                "/internal/tutor/chat",
                json={"user_id": 1, "messages": [{"role": "user", "content": "Q?"}]},
            )
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_exercise_stream(self, async_client):
        with patch("internal_api._get_exercise_agent") as mock_get:
            mock_agent = AsyncMock()
            mock_agent.run = AsyncMock(return_value={"questions": [{"q": "test"}]})
            mock_get.return_value = mock_agent
            
            response = await async_client.post(
                "/internal/exercise/generate",
                json={"topic": "Test", "count": 3},
            )
            assert response.status_code == 200


class TestPathEndpoint:
    @pytest.mark.asyncio
    async def test_path_response(self, async_client):
        with patch("internal_api._get_path_workflow") as mock_get:
            mock_agent = AsyncMock()
            mock_agent.run = AsyncMock(return_value={
                "steps": [{"order": 1, "topic": "Test", "status": "pending"}],
                "concept_graph": {"nodes": [], "edges": []},
            })
            mock_get.return_value = mock_agent
            
            response = await async_client.get("/internal/path/1")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            inner = data["data"]
            assert "steps" in inner
            assert "concept_graph" in inner
            assert isinstance(inner["steps"], list)
            assert isinstance(inner["concept_graph"], dict)

    @pytest.mark.asyncio
    async def test_path_step_structure(self, async_client):
        with patch("internal_api._get_path_workflow") as mock_get:
            mock_agent = AsyncMock()
            mock_agent.run = AsyncMock(return_value={
                "steps": [{"order": 1, "topic": "Test", "status": "pending"}],
                "concept_graph": {"nodes": [], "edges": []},
            })
            mock_get.return_value = mock_agent

            response = await async_client.get("/internal/path/1")
            data = response.json()
            steps = data["data"]["steps"]
            assert len(steps) > 0
            assert "order" in steps[0]
            assert "topic" in steps[0]
            assert "status" in steps[0]


class TestErrorHandling:
    def test_404(self, client):
        response = client.get("/internal/nonexistent")
        assert response.status_code == 404

    def test_invalid_method(self, client):
        response = client.get("/internal/profile/chat")
        assert response.status_code == 405


class TestMultimodalHelper:
    """internal_api 多模态消息构建工具函数"""

    def test_build_text_only_message(self):
        from internal_api import _build_multimodal_message
        msg = _build_multimodal_message("你好", None)
        assert msg == {"role": "user", "content": "你好"}

    def test_build_text_only_empty_images(self):
        from internal_api import _build_multimodal_message
        msg = _build_multimodal_message("你好", [])
        assert msg == {"role": "user", "content": "你好"}

    def test_build_with_single_image(self):
        from internal_api import _build_multimodal_message
        img = "data:image/jpeg;base64,/9j/4AAQ"
        msg = _build_multimodal_message("看这张图", [img])
        assert msg["role"] == "user"
        assert isinstance(msg["content"], list)
        assert msg["content"][0] == {"type": "text", "text": "看这张图"}
        assert msg["content"][1]["type"] == "image_url"
        assert msg["content"][1]["image_url"]["url"] == img

    def test_build_image_only_no_text(self):
        from internal_api import _build_multimodal_message
        img = "data:image/png;base64,iVBORw"
        msg = _build_multimodal_message("", [img])
        assert isinstance(msg["content"], list)
        assert len(msg["content"]) == 1
        assert msg["content"][0]["type"] == "image_url"

    def test_build_with_multiple_images(self):
        from internal_api import _build_multimodal_message
        imgs = [
            "data:image/jpeg;base64,/9j/...",
            "data:image/png;base64,iVBOR...",
        ]
        msg = _build_multimodal_message("对比这两张图", imgs)
        assert len(msg["content"]) == 3  # 1 text + 2 images

    def test_build_with_url_image(self):
        from internal_api import _build_multimodal_message
        img = "https://example.com/diagram.png"
        msg = _build_multimodal_message("这个图", [img])
        assert msg["content"][1]["image_url"]["url"] == img

    def test_build_raw_base64_adds_jpeg_prefix(self):
        from internal_api import _build_multimodal_message
        raw = "/9j/4AAQSkZJRg"  # 裸 base64，没有 data: 前缀
        msg = _build_multimodal_message("", [raw])
        url = msg["content"][0]["image_url"]["url"]
        assert url.startswith("data:image/jpeg;base64,")

    def test_reject_unsupported_mime(self):
        from internal_api import _build_multimodal_message
        img = "data:image/bmp;base64,Qk1K"  # BMP 不在白名单
        msg = _build_multimodal_message("测试", [img])
        # 图片被跳过，回退到纯文本
        assert msg == {"role": "user", "content": "测试"}

    def test_skip_empty_image_strings(self):
        from internal_api import _build_multimodal_message
        msg = _build_multimodal_message("测试", ["", "   ", "data:image/jpeg;base64,/9j/..."])
        assert len(msg["content"]) == 2  # 1 text + 1 valid image

    def test_extract_text_from_string(self):
        from internal_api import _extract_text_from_multimodal
        assert _extract_text_from_multimodal("hello") == "hello"

    def test_extract_text_from_multimodal_array(self):
        from internal_api import _extract_text_from_multimodal
        content = [
            {"type": "text", "text": "问题描述"},
            {"type": "image_url", "image_url": {"url": "data:..."}},
        ]
        assert _extract_text_from_multimodal(content) == "问题描述"

    def test_extract_text_from_empty(self):
        from internal_api import _extract_text_from_multimodal
        assert _extract_text_from_multimodal([]) == ""
        assert _extract_text_from_multimodal([{"type": "image_url", "image_url": {}}]) == ""


class TestMultimodalAPI:
    """多模态 tutor/chat API 测试"""

    @pytest.fixture(autouse=True)
    def _mock_deps(self):
        """mock conversation service + tutor agent，避免 DB 连接"""
        mock_conv = MagicMock()
        mock_conv.get_or_create_conversation = AsyncMock(return_value=MagicMock(id=1))
        mock_conv.load_history = AsyncMock(return_value=[])
        mock_conv.save_messages = AsyncMock()

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value={"response": "Answer"})

        with patch("internal_api.get_conversation_service", return_value=mock_conv), \
             patch("internal_api._get_tutor_agent", return_value=mock_agent):
            yield

    def test_tutor_with_images_field(self, client):
        """带 images 字段的请求不应被拒绝"""
        response = client.post(
            "/internal/tutor/chat",
            json={
                "user_id": 1,
                "content": "解释这张图",
                "images": ["data:image/jpeg;base64,/9j/4AAQ"],
            },
        )
        assert response.status_code == 200

    def test_tutor_with_empty_images(self, client):
        response = client.post(
            "/internal/tutor/chat",
            json={
                "user_id": 1,
                "content": "正常问题",
                "images": [],
            },
        )
        assert response.status_code == 200

    def test_tutor_with_too_many_images_rejected(self, client):
        """超过 5 张图片应被 Pydantic 拒绝"""
        response = client.post(
            "/internal/tutor/chat",
            json={
                "user_id": 1,
                "content": "test",
                "images": ["data:image/jpeg;base64,..."] * 6,
            },
        )
        assert response.status_code == 400
