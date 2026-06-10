import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock

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
        response = client.post("/internal/resources/generate", json={"user_id": 1})
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
                json={"topic": "Python", "user_id": 1, "student_profile": {}},
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

            response = await async_client.post(
                "/internal/path/1",
                json={"user_id": 1, "student_profile": {}},
            )
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

            response = await async_client.post(
                "/internal/path/1",
                json={"user_id": 1, "student_profile": {}},
            )
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
