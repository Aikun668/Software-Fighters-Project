import pytest

from app.services.capability_map import CENTER_EXECUTION_ORDER, INTENT_CENTER_MAP
from app.services.intent_extractor import (
    IntentExtractor,
    MultiIntentResult,
)


class TestExtractMulti:
    @pytest.fixture
    def extractor(self):
        return IntentExtractor(use_mock=True)

    @pytest.mark.asyncio
    async def test_multi_intent_detection(self, extractor):
        result = await extractor.extract_multi("规划Python学习路径，再出5道练习题")
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
        """钉住现行执行顺序合同：先答疑（auto），再产物（plan 最后）。"""
        order = CENTER_EXECUTION_ORDER
        assert order["auto"] < order["visualization"]
        assert order["visualization"] < order["resource"]
        assert order["resource"] < order["exercise"]
        assert order["exercise"] < order["plan"]
