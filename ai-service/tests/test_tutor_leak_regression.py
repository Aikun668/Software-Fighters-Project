"""Tutor 普通回答的专项回归：内部核查文本泄漏 + 无关画像注入（P4 评审 af-01/§3.3）。

两类必须防住的问题：
1. 内部核查/提示词文本出现在最终回答——历史真实回答尾部拼接过
   "内容核查提示：…以下内容置信度较低，仅供参考：…"（P4 评审 15/60 条命中）。
   泄漏源是 HallucinationGuard.verify_and_format 在 TutorAgent._respond_node
   里把 QA 管线内部文本追加进 response 正文，且发生在 sanity 检查之后，
   sanity 拦不住。
2. 无关画像字段进入最终回答上下文——画像只在会改变本轮回答时注入
   （ContextBuilder 答案塑形字段直通，其余字段需与当前话题词面相关）。

约定：检查器与守护不得改写正常回答正文；内部文本只允许留在日志里。
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.services.context_builder import ContextBuilder
from app.services.hallucination_guard import HallucinationGuard
from app.services.response_sanity import (
    SanityVerdict,
    check_response,
    run_with_sanity_check,
)

# 与 P4 评审 §3.3 引用的泄漏文本一致（管线内部 QA 措辞，不得出现在用户正文）
_QA_BLOCK_MARKERS = ("内容核查提示", "以下内容置信度较低")

_WEAK_CLAIMS_ANSWER = (
    "这是一段完全虚构的内容没有任何依据。"
    "第二个虚构说法也无法验证。"
    "第三个随机句子也一样无法查证。"
)


def _mock_kb(search_results):
    class _KB:
        def is_empty(self):
            return False

        def search(self, query, top_k=1):
            return search_results

    return _KB()


# ═══════════════════════════════════════════════════════════════
# 类 1：内部核查文本不得进入最终回答
# ═══════════════════════════════════════════════════════════════

class TestGuardDoesNotAppendQaBlock:
    """HallucinationGuard 不得把内部 QA 文本追加进用户可见正文。"""

    def test_low_confidence_returns_text_verbatim(self):
        guard = HallucinationGuard(_mock_kb([]))
        result = guard.verify_and_format(_WEAK_CLAIMS_ANSWER)
        # 无论置信度高低，正文原样返回；核查详情只进日志
        assert result == _WEAK_CLAIMS_ANSWER
        for marker in _QA_BLOCK_MARKERS:
            assert marker not in result

    def test_low_confidence_no_claim_echo(self):
        guard = HallucinationGuard(_mock_kb([]))
        result = guard.verify_and_format(_WEAK_CLAIMS_ANSWER)
        # 泄漏形态包含"复述正文句子"，同样不得出现
        assert "第二个虚构说法也无法验证" not in result.replace(
            _WEAK_CLAIMS_ANSWER, ""
        ) or result == _WEAK_CLAIMS_ANSWER


class TestRespondNodeNoQaBlock:
    """端到端复现 P4 af-01：AI 域 + 低置信回答，最终 response 不得含核查块。"""

    @pytest.mark.asyncio
    async def test_ai_domain_low_confidence_response_clean(self, monkeypatch):
        class _AiRouter:
            def classify(self, *args, **kwargs):
                return "ai"

            def should_inject_kb(self, *args, **kwargs):
                return True

            def should_inject_analogy(self, *args, **kwargs):
                return False

        async def clear_clarity(_message):
            return {"has_clear_goal": True, "has_blocker": False, "needs_clarification": False}

        with patch("app.agents.base_agent.create_llm", return_value=AsyncMock()):
            from app.agents.tutor_agent import TutorAgent
            agent = TutorAgent(use_mock_llm=True)

        async def stream(*args, **kwargs):
            yield _WEAK_CLAIMS_ANSWER

        agent.llm.chat_stream = stream
        monkeypatch.setattr("app.agents.tutor_agent.get_domain_router", lambda: _AiRouter())
        monkeypatch.setattr(agent, "_classify_clarity", clear_clarity)
        # 空 KB：所有声明 WEAK → 置信度 0.2，命中旧版追加路径
        monkeypatch.setattr("app.agents.tutor_agent.get_kb", lambda: _mock_kb([]))

        result = await agent._respond_node({
            "messages": [{"role": "user", "content": "反向传播为什么会导致梯度消失？"}],
            "student_profile": {},
            "knowledge_context": "",
        })

        assert result["response"] == _WEAK_CLAIMS_ANSWER
        for marker in _QA_BLOCK_MARKERS:
            assert marker not in result["response"]


class TestSanityFlagsInternalMarkers:
    """ResponseSanity 高置信拦截：回答回显内部核查/提示词标记（如历史脏数据模仿）。"""

    def test_qa_block_marker_is_user_safe_error(self):
        text = (
            "TCP 是传输层协议，负责可靠传输。\n---\n"
            "**内容核查提示：**\n- 超过50%的内容未在教材中找到对应验证"
        )
        r = check_response(text, "TCP是什么？")
        assert r.verdict is SanityVerdict.USER_SAFE_ERROR
        assert r.reason == "prompt_leak"
        assert r.error_code == "PROMPT_LEAK"

    def test_low_confidence_header_marker_is_user_safe_error(self):
        text = "梯度消失指梯度在反向传播中逐层衰减，最终接近于零。以下内容置信度较低，仅供参考。"
        r = check_response(text, "什么是梯度消失？")
        assert r.verdict is SanityVerdict.USER_SAFE_ERROR
        assert r.error_code == "PROMPT_LEAK"

    @pytest.mark.asyncio
    async def test_marker_leak_not_retried(self):
        calls = []

        async def generate(context):
            calls.append(context)
            return "反向传播通过链式法则逐层计算梯度。\n**内容核查提示：**"

        outcome = await run_with_sanity_check(generate, {"question": "什么是反向传播？"})
        assert outcome.text is None
        assert outcome.verdict is SanityVerdict.USER_SAFE_ERROR
        assert outcome.error_code == "PROMPT_LEAK"
        assert outcome.attempts == 1  # 高置信泄漏不重试
        assert len(calls) == 1

    def test_plain_uncertainty_wording_not_flagged(self):
        # 系统提示允许 tutor 标注"仅供参考"，单独出现不构成泄漏
        text = (
            "反向传播利用链式法则逐层计算梯度，连乘过多时梯度可能变得很小。"
            "具体数值与网络设置有关，这部分内容仅供参考。"
        )
        r = check_response(text, "什么是梯度消失？")
        assert r.verdict is SanityVerdict.ACCEPT
        assert r.text == text


# ═══════════════════════════════════════════════════════════════
# 类 2：无关画像字段不得进入最终回答上下文
# ═══════════════════════════════════════════════════════════════

_FULL_PROFILE = {
    "knowledge_base": 45,
    "cognitive_style": "偏好先直观后公式",
    "learning_goal": "通过软考",
    "weak_points": ["卷积神经网络"],
    "learning_pace": "每天1小时",
    "interest_direction": ["摄影", "旅游"],
}


class TestProfileRelevanceFiltering:
    """问 TCP 时不带入摄影兴趣；答案塑形字段照常注入。"""

    def test_tcp_question_excludes_irrelevant_interests(self):
        ctx = ContextBuilder().build(
            system="s",
            current_message="TCP 三次握手是什么？",
            student_profile=_FULL_PROFILE,
        )
        joined = " ".join(ctx.profile_facts)
        # 答案塑形字段：任何问题都生效
        assert "知识基础" in joined
        assert "学习风格" in joined
        # 与 TCP 无关的字段一律不注入
        assert "摄影" not in joined
        assert "旅游" not in joined
        assert "软考" not in joined
        assert "卷积" not in joined
        # 组装后的 system prompt 同样干净
        assert "摄影" not in ctx.system_prompt()

    def test_relevant_weak_points_still_injected(self):
        ctx = ContextBuilder().build(
            system="s",
            current_message="TCP 为什么需要三次握手？",
            student_profile={
                "weak_points": ["TCP 三次握手总是记不清"],
                "interest_direction": ["摄影"],
            },
        )
        assert any("TCP" in fact for fact in ctx.profile_facts)
        assert not any("摄影" in fact for fact in ctx.profile_facts)

    def test_cross_turn_reference_uses_recent_user_messages(self):
        # 上一轮在聊摄影，本轮问 TCP：当前话题决定注入，不受上轮兴趣干扰
        history = [
            {"role": "user", "content": "摄影构图有什么技巧？"},
            {"role": "assistant", "content": "可以试试三分法。"},
        ]
        ctx = ContextBuilder().build(
            system="s",
            current_message="TCP 和 UDP 的区别是什么？",
            history=history,
            student_profile=_FULL_PROFILE,
        )
        joined = " ".join(ctx.profile_facts)
        assert "摄影" not in joined
        assert "旅游" not in joined

    @pytest.mark.asyncio
    async def test_respond_node_system_prompt_excludes_interest(self, monkeypatch):
        """端到端：问 TCP，摄影兴趣不得进入最终 system prompt。"""

        class _GeneralRouter:
            def classify(self, *args, **kwargs):
                return "general"

            def should_inject_kb(self, *args, **kwargs):
                return False

            def should_inject_analogy(self, *args, **kwargs):
                return False

        async def clear_clarity(_message):
            return {"has_clear_goal": True, "has_blocker": False, "needs_clarification": False}

        with patch("app.agents.base_agent.create_llm", return_value=AsyncMock()):
            from app.agents.tutor_agent import TutorAgent
            agent = TutorAgent(use_mock_llm=True)

        captured = {}

        async def stream(messages, system_prompt=""):
            captured["system"] = system_prompt
            yield "TCP 三次握手用于确认双方的收发能力。"

        agent.llm.chat_stream = stream
        monkeypatch.setattr("app.agents.tutor_agent.get_domain_router", lambda: _GeneralRouter())
        monkeypatch.setattr(agent, "_classify_clarity", clear_clarity)

        await agent._respond_node({
            "messages": [{"role": "user", "content": "TCP 三次握手是什么？"}],
            "student_profile": _FULL_PROFILE,
            "knowledge_context": "",
        })

        assert "摄影" not in captured["system"]
        assert "学习风格" in captured["system"]  # 塑形字段保留
