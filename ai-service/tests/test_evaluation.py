import json
import pytest
from unittest.mock import AsyncMock, patch

from app.services.evaluation_service import (
    grade_choice,
    grade_short_answer,
    evaluate_session,
)
from app.services.evaluation_report import generate_report


class TestGradeChoice:
    def test_correct_answer_single_letter(self):
        result = grade_choice("A", "A")
        assert result["correct"] is True
        assert result["score"] == 1
        assert result["type"] == "choice"
        assert result["user_answer"] == "A"
        assert result["correct_answer"] == "A"

    def test_wrong_answer_single_letter(self):
        result = grade_choice("B", "A")
        assert result["correct"] is False
        assert result["score"] == 0
        assert result["correct_answer"] == "A"

    def test_correct_answer_multi_char(self):
        result = grade_choice("Python是一种解释型语言", "Python是一种解释型语言")
        assert result["correct"] is True
        assert result["score"] == 1

    def test_case_insensitive_matching(self):
        result = grade_choice("a", "A")
        assert result["correct"] is True
        assert result["score"] == 1

    def test_strip_whitespace_matching(self):
        result = grade_choice("  A  ", "A")
        assert result["correct"] is True
        assert result["score"] == 1

    def test_both_with_whitespace(self):
        result = grade_choice("  a  ", "  A  ")
        assert result["correct"] is True
        assert result["score"] == 1

    def test_full_option_match(self):
        result = grade_choice(
            "A. 使用决策树", "A. 使用决策树",
            choices=["A. 使用决策树", "B. 使用神经网络", "C. 使用SVM"]
        )
        assert result["correct"] is True
        assert result["score"] == 1

    def test_choices_passed_through(self):
        choices = ["A. 选项一", "B. 选项二"]
        result = grade_choice("A. 选项一", "A. 选项一", choices=choices)
        assert result["correct"] is True
        assert result["score"] == 1

    def test_multi_select_correct_order_independent(self):
        result = grade_choice("A,C", "C,A", multi=True)
        assert result["correct"] is True
        assert result["score"] == 1

    def test_multi_select_correct_same_order(self):
        result = grade_choice("A,B", "A,B", multi=True)
        assert result["correct"] is True

    def test_multi_select_wrong(self):
        result = grade_choice("A,C", "B,D", multi=True)
        assert result["correct"] is False
        assert result["score"] == 0

    def test_multi_select_partial(self):
        result = grade_choice("A,B", "A,B,C", multi=True)
        assert result["correct"] is False

    def test_multi_select_with_spaces(self):
        result = grade_choice("A, B", "B, A", multi=True)
        assert result["correct"] is True

    def test_points_parameter(self):
        result = grade_choice("A", "A", points=3)
        assert result["correct"] is True
        assert result["score"] == 3
        assert result["earned"] == 3
        assert result["max_score"] == 3

    def test_points_parameter_wrong_answer(self):
        result = grade_choice("B", "A", points=2)
        assert result["correct"] is False
        assert result["score"] == 0
        assert result["earned"] == 0

    def test_earned_and_max_score_fields(self):
        result = grade_choice("A", "A")
        assert result["earned"] == 1
        assert result["max_score"] == 1

    def test_feedback_field_correct(self):
        result = grade_choice("A", "A")
        assert "回答正确" in result["feedback"]

    def test_feedback_field_wrong(self):
        result = grade_choice("B", "A")
        assert "回答错误" in result["feedback"]
        assert result["correct_answer"] in result["feedback"]


class TestGradeShortAnswer:
    @pytest.mark.asyncio
    async def test_empty_answer(self):
        result = await grade_short_answer("", "参考答案")
        assert result["type"] == "short_answer"
        assert result["score"] == 0
        assert result["correct"] is False
        assert result["earned"] == 0
        assert result["max_score"] == 100
        assert "未作答" in result["feedback"]

    @pytest.mark.asyncio
    async def test_whitespace_only_answer(self):
        result = await grade_short_answer("   ", "参考答案")
        assert result["type"] == "short_answer"
        assert result["score"] == 0
        assert result["correct"] is False
        assert "未作答" in result["feedback"]

    @pytest.mark.asyncio
    async def test_llm_grading_returns_valid_structure(self):
        """真实 LLM 评分返回合法结构"""
        result = await grade_short_answer(
            "数据预处理包括归一化和标准化",
            "数据预处理包括归一化、标准化和数据增强",
            "评估准确性和完整性"
        )
        assert result["type"] == "short_answer"
        assert isinstance(result["score"], (int, float))
        assert 0 <= result["score"] <= 100
        assert result["earned"] == result["score"]
        assert result["max_score"] == 100
        assert isinstance(result["correct"], bool)
        assert isinstance(result["feedback"], str) and len(result["feedback"]) > 0
        assert isinstance(result["ai_comment"], str) and len(result["ai_comment"]) > 0
        assert isinstance(result["key_points_matched"], list)
        assert isinstance(result["key_points_missed"], list)

    @pytest.mark.asyncio
    async def test_llm_grading_short_vs_detailed(self):
        """简短回答 vs 详细参考答案：应有 miss 的要点"""
        result = await grade_short_answer(
            "机器学习是用数据训练模型",
            "机器学习是通过数据训练算法，使其能够从经验中学习和改进，涵盖监督学习、无监督学习和强化学习三大范式",
            "评估回答的完整度"
        )
        assert result["type"] == "short_answer"
        assert isinstance(result["score"], (int, float))
        assert isinstance(result["correct"], bool)
        assert isinstance(result["key_points_missed"], list)
        assert isinstance(result["key_points_matched"], list)

    @pytest.mark.asyncio
    async def test_llm_returns_non_json(self):
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value="这不是JSON，这是普通文本回复")
        with patch(
            "app.services.evaluation_service.get_llm_service",
            return_value=mock_llm,
        ):
            result = await grade_short_answer("回答", "参考答案")
        assert result["score"] == 0
        assert "评分失败" in result["feedback"]

    @pytest.mark.asyncio
    async def test_llm_call_failure(self):
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=Exception("LLM unavailable"))
        with patch(
            "app.services.evaluation_service.get_llm_service",
            return_value=mock_llm,
        ):
            result = await grade_short_answer("回答", "参考答案")
        assert result["score"] == 0
        assert "评分服务" in result["feedback"]
        assert result["key_points_matched"] == []
        assert result["key_points_missed"] == []

    @pytest.mark.asyncio
    async def test_json_with_extra_text(self):
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=(
            "这是我对你的评估：\n"
            + json.dumps({
                "score": 75,
                "feedback": "基本正确",
                "key_points_matched": ["要点一"],
                "key_points_missed": ["要点二"],
            })
            + "\n希望有帮助"
        ))
        with patch(
            "app.services.evaluation_service.get_llm_service",
            return_value=mock_llm,
        ):
            result = await grade_short_answer("回答", "参考答案")
        assert result["score"] == 75
        assert "基本正确" in result["feedback"]


class TestEvaluateSession:
    @pytest.mark.asyncio
    async def test_mixed_question_types(self):
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=json.dumps({
            "score": 80,
            "feedback": "不错",
            "key_points_matched": ["概念正确"],
            "key_points_missed": ["细节不足"],
        }))
        with patch(
            "app.services.evaluation_service.get_llm_service",
            return_value=mock_llm,
        ):
            answers = [
                {
                    "type": "choice",
                    "question": "Python是什么类型语言？",
                    "user_answer": "A",
                    "correct_answer": "A",
                    "module": "python_basics",
                },
                {
                    "type": "short_answer",
                    "question": "解释什么是机器学习？",
                    "user_answer": "机器学习是用数据训练模型",
                    "reference_answer": "机器学习是人工智能的一个分支",
                    "module": "ml_basics",
                },
            ]
            result = await evaluate_session(answers)
        assert len(result["results"]) == 2
        assert result["results"][0]["score"] == 1
        assert result["results"][1]["score"] == 80
        assert result["overall_score"] > 0
        assert result["total_score"] > 0
        assert result["max_score"] > 0

    @pytest.mark.asyncio
    async def test_total_score_calculation(self):
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=json.dumps({
            "score": 50,
            "feedback": "一般",
            "key_points_matched": ["部分正确"],
            "key_points_missed": ["很多遗漏"],
        }))
        with patch(
            "app.services.evaluation_service.get_llm_service",
            return_value=mock_llm,
        ):
            answers = [
                {
                    "type": "choice",
                    "question": "Q1",
                    "user_answer": "A",
                    "correct_answer": "A",
                    "module": "mod1",
                },
                {
                    "type": "choice",
                    "question": "Q2",
                    "user_answer": "B",
                    "correct_answer": "A",
                    "module": "mod1",
                },
                {
                    "type": "short_answer",
                    "question": "Q3",
                    "user_answer": "答案",
                    "reference_answer": "标准答案",
                    "module": "mod2",
                },
            ]
            result = await evaluate_session(answers)
        assert result["total_score"] == 51  # earned: 1 + 0 + 50
        assert result["max_score"] == 102  # max_score: 1 + 1 + 100
        assert result["overall_score"] == 50  # 51/102*100
        assert result["results"][0]["correct"] is True
        assert result["results"][1]["correct"] is False

    @pytest.mark.asyncio
    async def test_weak_point_detection(self):
        mock_llm_low = AsyncMock()
        mock_llm_low.chat = AsyncMock(return_value=json.dumps({
            "score": 30,
            "feedback": "很差",
            "key_points_matched": [],
            "key_points_missed": ["全部遗漏"],
        }))
        with patch(
            "app.services.evaluation_service.get_llm_service",
            return_value=mock_llm_low,
        ):
            answers = [
                {
                    "type": "choice",
                    "question": "Q1",
                    "user_answer": "B",
                    "correct_answer": "A",
                    "module": "weak_module",
                },
                {
                    "type": "short_answer",
                    "question": "Q2",
                    "user_answer": "不知道",
                    "reference_answer": "正确答案",
                    "module": "weak_module",
                },
                {
                    "type": "choice",
                    "question": "Q3",
                    "user_answer": "A",
                    "correct_answer": "A",
                    "module": "strong_module",
                },
            ]
            result = await evaluate_session(answers)
        assert "weak_module" in result["weak_modules"]
        assert "strong_module" not in result["weak_modules"]

    @pytest.mark.asyncio
    async def test_empty_answers(self):
        result = await evaluate_session([])
        assert result["results"] == []
        assert result["total_score"] == 0
        assert result["max_score"] == 0
        assert result["overall_score"] == 0
        assert result["weak_modules"] == []

    @pytest.mark.asyncio
    async def test_unknown_question_type_skipped(self):
        answers = [
            {
                "type": "fill_in_blank",
                "question": "填空",
                "user_answer": "xxx",
            }
        ]
        result = await evaluate_session(answers)
        assert len(result["results"]) == 0


class TestGenerateReport:
    def test_basic_report_structure(self):
        eval_results = {
            "results": [
                {"type": "choice", "question": "Q1", "module": "math", "score": 1, "correct": True},
                {"type": "choice", "question": "Q2", "module": "math", "score": 0, "correct": False},
                {"type": "short_answer", "question": "Q3", "module": "coding", "score": 85},
            ],
            "overall_score": 62,
            "weak_modules": ["math"],
        }
        report = generate_report(eval_results)
        assert report["overall_score"] == 62
        assert report["total_questions"] == 3
        assert report["correct_count"] == 2
        assert "math" in report["dimension_scores"]
        assert "coding" in report["dimension_scores"]
        assert "math" in report["weak_modules"]
        assert len(report["suggestions"]) > 0

    def test_dimension_scores_calculation(self):
        eval_results = {
            "results": [
                {"type": "choice", "question": "Q1", "module": "math", "score": 1, "correct": True, "earned": 1, "max_score": 1},
                {"type": "choice", "question": "Q2", "module": "math", "score": 0, "correct": False, "earned": 0, "max_score": 1},
                {"type": "short_answer", "question": "Q3", "module": "coding", "score": 90, "earned": 90, "max_score": 100},
                {"type": "short_answer", "question": "Q4", "module": "coding", "score": 70, "earned": 70, "max_score": 100},
            ],
            "overall_score": 75,
            "weak_modules": [],
        }
        report = generate_report(eval_results)
        assert report["dimension_scores"]["math"] == 50  # round((1+0)/(1+1)*100)

    def test_suggestions_for_low_score(self):
        eval_results = {
            "results": [],
            "overall_score": 45,
            "weak_modules": ["module_a", "module_b"],
        }
        report = generate_report(eval_results)
        assert any("重新学习" in s for s in report["suggestions"])

    def test_suggestions_for_medium_score(self):
        eval_results = {
            "results": [],
            "overall_score": 70,
            "weak_modules": ["module_a"],
        }
        report = generate_report(eval_results)
        assert any("深入练习" in s for s in report["suggestions"])

    def test_suggestions_for_high_score(self):
        eval_results = {
            "results": [],
            "overall_score": 90,
            "weak_modules": [],
        }
        report = generate_report(eval_results)
        assert any("挑战更高难度" in s for s in report["suggestions"])

    def test_weak_area_suggestions(self):
        eval_results = {
            "results": [
                {"type": "choice", "question": "Q1", "module": "math", "score": 0, "correct": False},
            ],
            "overall_score": 0,
            "weak_modules": ["math"],
        }
        report = generate_report(eval_results)
        assert any("math" in s for s in report["suggestions"])

    def test_with_student_profile(self):
        student_profile = {
            "knowledge_base": 50,
            "cognitive_style": "visual",
            "learning_goal": "学AI",
            "weak_points": ["Python"],
            "learning_pace": "fast",
            "interest_direction": ["ML"],
        }
        eval_results = {
            "results": [
                {"type": "choice", "question": "Q1", "module": "math", "score": 0, "correct": False},
                {"type": "short_answer", "question": "Q2", "module": "coding", "score": 55},
            ],
            "overall_score": 27,
            "weak_modules": ["math", "coding"],
        }
        report = generate_report(eval_results, student_profile)
        assert report["recommended_weak_points"] is not None
        assert "math" in report["recommended_weak_points"]
        assert "coding" in report["recommended_weak_points"]

    def test_profile_with_empty_weak_points(self):
        student_profile = {"weak_points": None, "knowledge_base": 0}
        eval_results = {
            "results": [
                {"type": "choice", "question": "Q1", "module": "math", "score": 0, "correct": False},
            ],
            "overall_score": 0,
            "weak_modules": ["math"],
        }
        report = generate_report(eval_results, student_profile)
        assert "math" in report["recommended_weak_points"]

    def test_correct_count_with_score_threshold(self):
        eval_results = {
            "results": [
                {"type": "choice", "question": "Q1", "module": "m", "score": 1, "correct": True},
                {"type": "short_answer", "question": "Q2", "module": "m", "score": 40},
                {"type": "short_answer", "question": "Q3", "module": "m", "score": 85},
            ],
            "overall_score": 50,
            "weak_modules": [],
        }
        report = generate_report(eval_results)
        assert report["correct_count"] == 2


class TestIncrementalUpdate:
    def _make_mock_profile(self, knowledge_base=50, weak_points=None):
        from unittest.mock import MagicMock
        p = MagicMock()
        p.knowledge_base = knowledge_base
        p.weak_points = weak_points or []
        return p

    @pytest.mark.asyncio
    async def test_incremental_update_merges_weak_points(self):
        from unittest.mock import AsyncMock, MagicMock
        from app.services.profile_service import ProfileService, get_db
        from app.models.profile import StudentProfile

        service = ProfileService()
        mock_profile = self._make_mock_profile(50, ["Python"])
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_profile
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.profile_service.get_db", return_value=mock_session):
            await service.incremental_update(1, {
                "recommended_weak_points": ["math", "Python"],
                "overall_score": 80,
            })
        assert "math" in mock_profile.weak_points
        assert "Python" in mock_profile.weak_points
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_incremental_update_knowledge_base(self):
        from unittest.mock import AsyncMock, MagicMock
        from app.services.profile_service import ProfileService, get_db

        service = ProfileService()
        mock_profile = self._make_mock_profile(30, [])
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_profile
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.profile_service.get_db", return_value=mock_session):
            await service.incremental_update(1, {
                "recommended_weak_points": [],
                "overall_score": 70,
            })
        expected_kb = int(30 * 0.7 + 70 * 0.3)
        assert mock_profile.knowledge_base == expected_kb

    @pytest.mark.asyncio
    async def test_incremental_update_knowledge_base_clamped(self):
        from unittest.mock import AsyncMock, MagicMock
        from app.services.profile_service import ProfileService, get_db

        service = ProfileService()
        mock_profile = self._make_mock_profile(98, [])
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_profile
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.profile_service.get_db", return_value=mock_session):
            await service.incremental_update(1, {
                "recommended_weak_points": [],
                "overall_score": 95,
            })
        assert mock_profile.knowledge_base <= 100

    @pytest.mark.asyncio
    async def test_incremental_update_no_profile(self):
        from unittest.mock import AsyncMock, MagicMock
        from app.services.profile_service import ProfileService

        service = ProfileService()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.profile_service.get_db", return_value=mock_session):
            await service.incremental_update(999, {
                "recommended_weak_points": ["math"],
                "overall_score": 80,
            })
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_incremental_update_save_failure(self):
        from unittest.mock import AsyncMock, MagicMock
        from app.services.profile_service import ProfileService

        service = ProfileService()
        mock_profile = self._make_mock_profile(50, ["Python"])
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_profile
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock(side_effect=Exception("DB error"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.profile_service.get_db", return_value=mock_session):
            await service.incremental_update(1, {
                "recommended_weak_points": [],
                "overall_score": 80,
            })
