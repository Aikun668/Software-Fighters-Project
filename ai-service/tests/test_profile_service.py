import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.profile_service import ProfileService, get_profile_service


class TestProfileService:
    @pytest.fixture
    def service(self):
        return ProfileService()

    @pytest.fixture
    def mock_db(self):
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.close = AsyncMock()
        return mock_session

    @pytest.mark.asyncio
    async def test_get_profile_found(self, service, mock_db):
        mock_profile = MagicMock()
        mock_profile.knowledge_base = 50
        mock_profile.cognitive_style = "visual"
        mock_profile.learning_goal = "掌握深度学习"
        mock_profile.weak_points = ["数学"]
        mock_profile.learning_pace = "moderate"
        mock_profile.interest_direction = ["CV"]
        mock_profile.tag_weights = {}
        mock_profile.stability_counter = {}
        mock_profile.entries = {}
        mock_profile.audit_counter = 0

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_profile
        mock_db.execute.return_value = mock_result

        with patch("app.services.profile_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            profile = await service.get_profile(1)

        assert profile is not None
        assert profile["knowledge_base"] == 50
        assert profile["cognitive_style"] == "visual"
        assert profile["weak_points"] == ["数学"]
        assert profile["interest_direction"] == ["CV"]
        assert "entries" in profile
        assert "audit_counter" in profile

    @pytest.mark.asyncio
    async def test_get_profile_not_found(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch("app.services.profile_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            profile = await service.get_profile(999)

        assert profile is None

    @pytest.mark.asyncio
    async def test_get_profile_db_error(self, service, mock_db):
        mock_db.execute.side_effect = Exception("DB error")

        with patch("app.services.profile_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            profile = await service.get_profile(1)

        assert profile is None

    @pytest.mark.asyncio
    async def test_save_profile(self, service, mock_db):
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        with patch("app.services.profile_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            await service.save_profile(1, {
                "knowledge_base": 60,
                "cognitive_style": "visual",
                "learning_goal": "test",
                "weak_points": ["math"],
                "learning_pace": "fast",
                "interest_direction": ["nlp"],
            })

        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_profile_db_error(self, service, mock_db):
        mock_db.execute.side_effect = Exception("DB error")

        with patch("app.services.profile_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            await service.save_profile(1, {"knowledge_base": 50})

    @pytest.mark.asyncio
    async def test_get_profile_after_save(self, service, mock_db):
        mock_profile = MagicMock()
        mock_profile.knowledge_base = 75
        mock_profile.cognitive_style = "auditory"
        mock_profile.learning_goal = "test goal"
        mock_profile.weak_points = ["python"]
        mock_profile.learning_pace = "slow"
        mock_profile.interest_direction = ["rl"]
        mock_profile.tag_weights = {}
        mock_profile.stability_counter = {}
        mock_profile.entries = {}
        mock_profile.audit_counter = 0

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_profile
        mock_db.execute.return_value = mock_result

        with patch("app.services.profile_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            profile = await service.get_profile(1)

        assert profile["knowledge_base"] == 75
        assert profile["cognitive_style"] == "auditory"

    def test_get_profile_service_singleton(self):
        s1 = get_profile_service()
        s2 = get_profile_service()
        assert s1 is s2
