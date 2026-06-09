import pytest
from unittest.mock import AsyncMock, patch

from app.services.profile_service import ProfileService, get_profile_service


class TestProfileService:
    @pytest.fixture
    def service(self):
        svc = ProfileService()
        svc._client = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_get_profile_found(self, service):
        service._client.get_profile = AsyncMock(return_value={
            "knowledge_base": 50, "cognitive_style": "visual",
            "learning_goal": "掌握深度学习", "weak_points": ["数学"],
            "learning_pace": "moderate", "interest_direction": ["CV"],
            "tag_weights": {}, "stability_counter": {},
            "entries": {}, "audit_counter": 0,
        })

        profile = await service.get_profile(1)

        assert profile is not None
        assert profile["knowledge_base"] == 50
        assert profile["cognitive_style"] == "visual"
        assert profile["weak_points"] == ["数学"]
        assert profile["interest_direction"] == ["CV"]
        assert "entries" in profile
        assert "audit_counter" in profile

    @pytest.mark.asyncio
    async def test_get_profile_not_found(self, service):
        service._client.get_profile = AsyncMock(return_value=None)

        profile = await service.get_profile(999)

        assert profile is None

    @pytest.mark.asyncio
    async def test_get_profile_db_error(self, service):
        service._client.get_profile = AsyncMock(side_effect=Exception("API error"))

        profile = await service.get_profile(1)

        assert profile is None

    @pytest.mark.asyncio
    async def test_save_profile(self, service):
        service._client.upsert_profile = AsyncMock(return_value={"user_id": 1})

        await service.save_profile(1, {
            "knowledge_base": 60, "cognitive_style": "visual",
            "learning_goal": "test", "weak_points": ["math"],
            "learning_pace": "fast", "interest_direction": ["nlp"],
        })

        service._client.upsert_profile.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_profile_db_error(self, service):
        service._client.upsert_profile = AsyncMock(side_effect=Exception("API error"))

        # 不应抛出异常
        await service.save_profile(1, {"knowledge_base": 50})

    @pytest.mark.asyncio
    async def test_get_profile_after_save(self, service):
        """验证 get_profile 返回正确的画像字典"""
        service._client.get_profile = AsyncMock(return_value={
            "knowledge_base": 75, "cognitive_style": "auditory",
            "learning_goal": "test goal", "weak_points": ["python"],
            "learning_pace": "slow", "interest_direction": ["rl"],
            "tag_weights": {}, "stability_counter": {},
            "entries": {}, "audit_counter": 0,
        })

        profile = await service.get_profile(1)

        assert profile["knowledge_base"] == 75
        assert profile["cognitive_style"] == "auditory"

    def test_get_profile_service_singleton(self):
        s1 = get_profile_service()
        s2 = get_profile_service()
        assert s1 is s2
