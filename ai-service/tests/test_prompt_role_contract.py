"""Prompt 角色契约：平台人设只能出现在 system 栏，绝不能混进 user 消息。

背景（本轮修复的根因）：
``BaseAgent._load_extra_prompt`` 曾无条件转发给 ``_load_prompt``，于是所有
``key="user_template"`` / ``key="plan_user"`` / ``key="quiz_user"`` 之类的调用点，
取到的用户模板都被粘上了 ``SAFETY_SYSTEM_PROMPT``——那段文字自称
"运行在人工智能课程教学平台中，以人工智能课程为主"。

后果：user 消息里出现「用户自称是 AI 平台助手」。模型据此把主题锚定到 AI，
即使用户要求"出六级选词填空的题"，也会输出人工智能题目（真实故障）。

这组用例锁两件事：
  1. user 角色的模板**不含**平台人设；
  2. system 角色的提示词**必须含**平台人设（否则修完第 1 条会丢掉安全边界）。
"""

import pytest

from app.agents.base_agent import SAFETY_SYSTEM_PROMPT

# 平台身份的唯一标识串：出现在 user 栏即为泄漏
PERSONA_MARKER = "人工智能课程教学平台"


class TestUserRoleKeyClassification:
    """key 的角色判定：含 user 即用户消息，其余为 system。"""

    @pytest.mark.parametrize("key", [
        "user", "user_template", "user_plan", "plan_user", "quiz_user",
        "user_solve", "user_review", "implement_user",
    ])
    def test_user_keys_recognized(self, key):
        from app.agents.base_agent import BaseAgent
        assert BaseAgent._is_user_role_key(key) is True, f"{key} 应判为 user 角色"

    @pytest.mark.parametrize("key", [
        "system", "system_plan", "system_solve", "system_review",
        "implement_system", "plan_system", "quiz_system",
    ])
    def test_system_keys_recognized(self, key):
        from app.agents.base_agent import BaseAgent
        assert BaseAgent._is_user_role_key(key) is False, f"{key} 应判为 system 角色"

    def test_empty_key_defaults_to_system(self):
        """空 key 按 system 处理：宁可多带人设，不可静默丢弃。"""
        from app.agents.base_agent import BaseAgent
        assert BaseAgent._is_user_role_key("") is False
        assert BaseAgent._is_user_role_key(None) is False


class TestExerciseAgentPromptRoles:
    """出题 Agent —— 本轮真实故障现场。"""

    @pytest.fixture(scope="class")
    def agent(self):
        from app.agents.exercise_agent import ExerciseAgent
        return ExerciseAgent(use_mock_llm=True)

    def test_plan_user_template_has_no_persona(self, agent):
        """plan_user 是用户消息模板，不得含平台身份。"""
        tpl = agent._load_extra_prompt("pipeline.yaml", key="plan_user")
        assert tpl.strip(), "模板不应为空（否则用例本身失效）"
        assert PERSONA_MARKER not in tpl
        assert SAFETY_SYSTEM_PROMPT not in tpl

    def test_quiz_user_template_has_no_persona(self, agent):
        tpl = agent._load_extra_prompt("pipeline.yaml", key="quiz_user")
        assert tpl.strip()
        assert PERSONA_MARKER not in tpl
        assert SAFETY_SYSTEM_PROMPT not in tpl

    def test_plan_system_keeps_persona(self, agent):
        """system 栏必须带回平台人设，否则安全边界丢失。"""
        sys_prompt = agent._load_prompt(
            "pipeline.yaml", conditions={"warmup": False}, key="plan_system"
        )
        assert PERSONA_MARKER in sys_prompt
        assert SAFETY_SYSTEM_PROMPT in sys_prompt

    def test_quiz_system_keeps_persona(self, agent):
        sys_prompt = agent._load_prompt(
            "pipeline.yaml", conditions={"warmup": False}, key="quiz_system"
        )
        assert PERSONA_MARKER in sys_prompt
        assert SAFETY_SYSTEM_PROMPT in sys_prompt

    def test_warmup_condition_still_applies(self, agent):
        """修复不得破坏 {{#if warmup}} 条件块渲染。"""
        warm = agent._load_prompt(
            "pipeline.yaml", conditions={"warmup": True}, key="quiz_system"
        )
        cold = agent._load_prompt(
            "pipeline.yaml", conditions={"warmup": False}, key="quiz_system"
        )
        assert "回归热身题约束" in warm
        assert "回归热身题约束" not in cold


class TestOtherAgentsPromptRoles:
    """抽查其它 Agent：user 模板干净、system 带人设。"""

    def test_flashcard_prompt_roles(self):
        from app.agents.flashcard_agent import FlashCardAgent
        agent = FlashCardAgent(use_mock_llm=True)

        user_tpl = agent._load_extra_prompt("system.yaml", key="user_template")
        assert PERSONA_MARKER not in user_tpl

        sys_tpl = agent._load_extra_prompt("system.yaml", key="system")
        assert PERSONA_MARKER in sys_tpl

    def test_instance_system_prompt_keeps_persona(self):
        """self.system_prompt（构造期加载）仍带人设 —— 安全边界未削弱。"""
        from app.agents.exercise_agent import ExerciseAgent
        agent = ExerciseAgent(use_mock_llm=True)
        assert SAFETY_SYSTEM_PROMPT in agent.system_prompt

    def test_goal_agent_user_template_clean(self):
        from app.agents.goal_agent import GoalAgent
        agent = GoalAgent(use_mock_llm=True)
        user_tpl = agent._load_extra_prompt("system.yaml", key="user_template")
        assert PERSONA_MARKER not in user_tpl


class TestUserTemplateIsSolelyUserFacing:
    """端到端：模拟出题链路发出的 user 消息，确认不含平台身份。"""

    def test_plan_user_message_content(self):
        from app.agents.exercise_agent import ExerciseAgent
        from app.utils.prompt_loader import interpolate_variables

        agent = ExerciseAgent(use_mock_llm=True)
        tpl = agent._load_extra_prompt("pipeline.yaml", key="plan_user")
        filled = interpolate_variables(tpl, {
            "topic": "六级选词 填空 题目",
            "count": "3",
            "difficulty": "medium",
            "weak_points": "无",
            "purpose": "",
            "strategy_hint": "",
        })

        # 用户消息里只该有用户自己的诉求，不该有平台自我介绍
        assert PERSONA_MARKER not in filled
        assert "六级选词" in filled, "用户真实诉求必须保留"
        assert "3" in filled
