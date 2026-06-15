import pytest

from app.services.intent_extractor import (
    INTENT_CENTER_MAP,
    IntentExtractor,
    MultiIntentResult,
)


class TestExtractMulti:
    @pytest.fixture
    def extractor(self):
        return IntentExtractor(use_mock=True)

    @pytest.mark.asyncio
    async def test_multi_intent_detection(self, extractor):
        result = await extractor.extract_multi("规划Python路径并出3道题")
        assert isinstance(result, MultiIntentResult)
        assert len(result.intents) >= 2
        intent_names = [r.intent for r in result.intents]
        assert "learning_path" in intent_names
        assert "exercise_gen" in intent_names
        assert result.is_clear is True

    @pytest.mark.asyncio
    async def test_max_intents_clamped(self, extractor):
        result = await extractor.extract_multi("规划路径出题生成资源画知识图谱")
        assert len(result.intents) <= 3

    @pytest.mark.asyncio
    async def test_unclear_message_low_confidence(self, extractor):
        result = await extractor.extract_multi("随便聊聊")
        assert result.is_clear is False or result.intents[0].intent == "tutor_question"

    @pytest.mark.asyncio
    async def test_empty_message_returns_inquiry(self, extractor):
        result = await extractor.extract_multi("   ")
        assert result.is_clear is False


class TestIntentCenterMap:
    def test_all_intents_mapped(self):
        from app.services.intent_extractor import INTENT_TYPES
        for intent in INTENT_TYPES.__args__:
            assert intent in INTENT_CENTER_MAP

    def test_center_order(self):
        from app.services.intent_extractor import _CENTER_EXECUTION_ORDER
        assert _CENTER_EXECUTION_ORDER["plan"] < _CENTER_EXECUTION_ORDER["auto"]
        assert _CENTER_EXECUTION_ORDER["auto"] < _CENTER_EXECUTION_ORDER["resource"]
