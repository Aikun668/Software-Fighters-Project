"""T4-C 资源域闭环：code_example / flashcard_gen 的 mock 参数提取产出 suggested_types。

锁定：code_example 产出 topic + language + suggested_types=["code"]；
flashcard_gen 产出 topic + count + suggested_types=["flashcard"]。
这样 ResourceCenter 能 type_direct 直通对应 Specialist，不再词根碰运气。
"""

from app.services.intent_extractor import (
    _mock_extract_params,
    _score_intent,
    extract_count,
    INTENT_REGISTRY,
)


class TestCodeExampleParams:
    def test_code_example_has_suggested_code(self):
        p = _mock_extract_params("code_example", "给我一个快速排序的代码示例")
        assert p.get("suggested_types") == ["code"]
        assert p.get("topic")

    def test_code_example_language_detection(self):
        p = _mock_extract_params("code_example", "给我一个java的快排代码")
        assert p.get("language") == "java"

    def test_code_example_default_language(self):
        p = _mock_extract_params("code_example", "给我一个快排代码")
        assert p.get("language") == "python"


class TestFlashcardParams:
    def test_flashcard_has_suggested_flashcard(self):
        p = _mock_extract_params("flashcard_gen", "帮我生成关于操作系统的闪卡")
        assert p.get("suggested_types") == ["flashcard"]
        assert p.get("topic")

    def test_flashcard_count(self):
        p = _mock_extract_params("flashcard_gen", "帮我生成10张关于进程的闪卡")
        assert p.get("count") == 10


class TestChineseNumeralCount:
    """FINAL 实测修复（会话 98/99）：'一道' 此前落到默认 3 道。"""

    def test_chinese_one(self):
        assert extract_count("帮我生成一道高数题", 3) == 1

    def test_chinese_two(self):
        assert extract_count("给我来两道题", 3) == 2

    def test_chinese_ten_plus(self):
        assert extract_count("出十五道题", 3) == 15

    def test_arabic_still_works(self):
        assert extract_count("帮我出5道题", 3) == 5

    def test_vague_falls_back_to_default(self):
        assert extract_count("给我来几道题", 3) == 3

    def test_exercise_params_use_chinese_count(self):
        p = _mock_extract_params("exercise_gen", "帮我生成一道高数题，很难的那种")
        assert p.get("count") == 1

    def test_flashcard_params_use_chinese_count(self):
        p = _mock_extract_params("flashcard_gen", "帮我生成三张闪卡")
        assert p.get("count") == 3


class TestCodeExampleNotFooledByWriteVerb:
    """FINAL 实测：通用"写一个/写个"不许把"写一个计划/作文"判成要代码。"""

    def _ce(self):
        return [d for d in INTENT_REGISTRY if d.intent == "code_example"][0]

    def test_write_a_plan_is_not_code(self):
        assert _score_intent("希望你写一个计划", self._ce()) == 0.0
        assert _score_intent("写一个学习计划", self._ce()) == 0.0

    def test_write_an_essay_is_not_code(self):
        assert _score_intent("帮我写一个作文", self._ce()) == 0.0

    def test_real_code_requests_still_score(self):
        assert _score_intent("给我一个快速排序的代码示例", self._ce()) > 0
        assert _score_intent("帮我写一个快速排序", self._ce()) > 0
        assert _score_intent("写个函数", self._ce()) > 0
