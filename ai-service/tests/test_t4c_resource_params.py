"""T4-C 资源域闭环：code_example / flashcard_gen 的 mock 参数提取产出 suggested_types。

锁定：code_example 产出 topic + language + suggested_types=["code"]；
flashcard_gen 产出 topic + count + suggested_types=["flashcard"]。
这样 ResourceCenter 能 type_direct 直通对应 Specialist，不再词根碰运气。
"""

from app.services.intent_extractor import _mock_extract_params


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
