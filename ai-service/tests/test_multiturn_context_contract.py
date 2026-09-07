"""普通聊天多轮上下文合同测试（不提交 · 用户专项任务）。

合同：
1. 第二轮追问能拿到第一轮语义（LLM 收到的上下文含第一轮完整轮次，
   或摘要中保留第一轮确认主题）。
2. 空 assistant/user 消息不得进入下一轮上下文（历史含空消息时被过滤）。
3. 无历史的旧调用保持兼容（messages=[] 不崩，摘要为空）。
4. conversation_id 从 ChatCenter 上下文一路传到 TutorAgent state。
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.tutor_agent import TutorAgent
from app.centers.auto_center import AutoCenter
from app.centers.schemas import CenterTask
from app.services.context_builder import ContextBuilder, group_turns
from app.services.summary_maintainer import SummaryMaintainer

# ── 1. 空消息不得进入上下文 ──────────────────────────────────

class TestEmptyMessagesFiltered:
    def test_group_turns_skips_empty_content(self):
        history = [
            {"role": "user", "content": "什么是进程？"},
            {"role": "assistant", "content": ""},          # 历史上的空回复
            {"role": "assistant", "content": "   "},       # 纯空白
            {"role": "user", "content": "那线程呢？"},
            {"role": "assistant", "content": "线程是 CPU 调度的基本单位。"},
        ]
        turns = group_turns(history)
        flat = [m for t in turns for m in t]
        assert all(str(m.get("content", "")).strip() for m in flat), \
            f"空消息不得进入轮次: {flat}"

    def test_built_context_drops_empty_history_messages(self):
        history = [
            {"role": "user", "content": "什么是进程？"},
            {"role": "assistant", "content": ""},
            {"role": "user", "content": "那线程呢？"},
        ]
        built = ContextBuilder().build(
            system="系统指令",
            current_message="那线程呢？",
            history=history,
        )
        msgs = built.messages()
        assert msgs[-1] == {"role": "user", "content": "那线程呢？"}
        for m in msgs[:-1]:
            assert str(m.get("content", "")).strip(), f"空消息进入上下文: {msgs}"
        assert not any(
            m.get("role") == "assistant" and not str(m.get("content", "")).strip()
            for m in built.recent_turns
        )

    def test_summary_rebuild_ignores_empty_messages(self):
        history = [
            {"role": "user", "content": "什么是进程？"},
            {"role": "assistant", "content": ""},
        ]
        state = SummaryMaintainer().rebuild_from_history(history, current_message="那线程呢？")
        assert "进程" in state.to_text()


# ── 2. 摘要跨轮保留（旧实现下一轮清零） ──────────────────────

class TestSummarySurvivesAcrossTurns:
    def test_correction_topic_kept_on_followup_turn(self):
        """轮2 纠正主题后，轮3 追问时摘要仍含被纠正后的主题。"""
        maintainer = SummaryMaintainer()

        # 轮2：纠正（旧实现：当轮算出摘要，轮3 丢失）
        history_t2 = [
            {"role": "user", "content": "TCP 建立连接为什么握手是三次？"},
            {"role": "assistant", "content": "三次握手确保双方收发能力都被确认。"},
        ]
        state_t2 = maintainer.rebuild_from_history(history_t2, current_message="不是，我说的是挥手，不是握手。")
        assert "挥手" in state_t2.to_text()

        # 轮3：追问——摘要必须仍含"挥手"
        history_t3 = history_t2 + [
            {"role": "assistant", "content": "好的，我们来谈挥手（四次挥手）。"},
        ]
        state_t3 = maintainer.rebuild_from_history(history_t3, current_message="为什么挥手要四次？")
        assert "挥手" in state_t3.to_text(), \
            "第三轮摘要必须保留第二轮纠正的主题（跨轮保留）"

    def test_rebuild_reflects_latest_topic(self):
        """多轮换题时，当前主题反映用户最近一次表态。"""
        maintainer = SummaryMaintainer()
        history = [
            {"role": "user", "content": "我想问虚拟内存"},
            {"role": "assistant", "content": "虚拟内存是……"},
            {"role": "user", "content": "不是，我说的是进程调度"},
            {"role": "assistant", "content": "进程调度算法有……"},
        ]
        state = maintainer.rebuild_from_history(history, current_message="为什么？")
        assert state.current_topic and "调度" in state.current_topic

    def test_rebuild_is_deterministic(self):
        """同一输入重复重建结果一致（每轮全量重建等价于持久化）。"""
        history = [
            {"role": "user", "content": "讲讲梯度消失"},
            {"role": "assistant", "content": "深层网络中梯度连乘变小……"},
        ]
        m = SummaryMaintainer()
        s1 = m.rebuild_from_history(history, current_message="怎么解决？")
        s2 = m.rebuild_from_history(history, current_message="怎么解决？")
        assert s1.to_text() == s2.to_text()


# ── 3. 无历史兼容 ────────────────────────────────────────────

class TestNoHistoryCompat:
    def test_empty_history_build(self):
        built = ContextBuilder().build(
            system="系统指令", current_message="什么是递归？", history=None,
        )
        assert built.messages() == [{"role": "user", "content": "什么是递归？"}]
        assert built.summary == ""

    def test_rebuild_empty_history(self):
        state = SummaryMaintainer().rebuild_from_history([], current_message="你好")
        assert isinstance(state.to_text(), str)


# ── 4. 端到端：TutorAgent 真实流转（fake LLM 截获上下文） ────

class _FakeLLM:
    """记录入参、按脚本输出的 LLM 替身。"""

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls: list[dict] = []

    async def chat_stream(self, messages, system_prompt="", **kwargs):
        self.calls.append({
            "messages": [dict(m) for m in messages],
            "system_prompt": system_prompt,
        })
        reply = self.replies.pop(0) if self.replies else ""
        for ch in reply:
            yield ch


def _make_tutor(llm: _FakeLLM) -> TutorAgent:
    tutor = TutorAgent(use_mock_llm=True)
    tutor.llm = llm
    tutor._clarity_llm = object()  # 防误用；_classify_clarity 会被整体替换
    tutor._classify_clarity = AsyncMock(
        return_value={"has_clear_goal": True, "has_blocker": False, "needs_clarification": False}
    )

    class _EmptyKB:
        def is_empty(self):
            return True

    tutor.get_kb = lambda: _EmptyKB()  # type: ignore[assignment]
    return tutor


@pytest.mark.asyncio(loop_scope="function")
class TestTutorEndToEndMultiturn:
    async def test_auto_center_successfully_forwards_conversation_id(self):
        """AutoCenter 正常答疑路径不得因 conversation_id 传递失败而降级为 error。"""
        captured: dict = {}

        class SuccessfulTutor:
            async def run(self, state):
                captured.update(state)
                return {"response": "进程是资源分配的基本单位。", "domain": "general"}

        task = CenterTask(
            mode="auto",
            intent="tutor_question",
            input="什么是进程？",
            params={"question": "什么是进程？"},
            context={
                "messages": [{"role": "user", "content": "什么是进程？"}],
                "student_profile": {},
                "conversation_id": 42,
            },
            sequence=0,
        )

        result = await AutoCenter(tutor_agent=SuccessfulTutor()).execute(task)

        assert result.event_type == "content"
        assert result.payload["response"] == "进程是资源分配的基本单位。"
        assert captured["conversation_id"] == 42

    async def test_second_turn_receives_first_turn_semantics(self):
        """第二轮追问发给 LLM 的上下文必须包含第一轮的完整问答。"""
        llm = _FakeLLM(replies=["线程是 CPU 调度的基本单位，与进程共享内存。"])
        tutor = _make_tutor(llm)

        history = [
            {"role": "user", "content": "什么是进程？"},
            {"role": "assistant", "content": "进程是操作系统资源分配的基本单位。"},
        ]
        state = await tutor.run({
            "messages": history + [{"role": "user", "content": "那线程呢？"}],
            "student_profile": {},
            "style": "standard",
            "conversation_id": 42,
        })

        assert state.get("response"), f"应有正常回答: {state}"
        assert llm.calls, "LLM 应被调用"
        sent = llm.calls[-1]["messages"]
        # 第一轮语义在场
        assert any(
            m.get("role") == "user" and "进程" in str(m.get("content", ""))
            for m in sent
        ), f"第一轮问题缺失: {sent}"
        assert any(
            m.get("role") == "assistant" and "资源分配" in str(m.get("content", ""))
            for m in sent
        ), f"第一轮回答缺失: {sent}"
        # 当前消息在最后 user 位置
        assert sent[-1]["role"] == "user" and sent[-1]["content"] == "那线程呢？"
        # conversation_id 透传进 state
        assert state.get("conversation_id") == 42

    async def test_empty_llm_output_returns_error_and_no_content(self):
        """sanity 失败（空回答）→ 返回错误码；空正文不作为 content 回给调用方。"""
        llm = _FakeLLM(replies=["", ""])
        tutor = _make_tutor(llm)

        state = await tutor.run({
            "messages": [{"role": "user", "content": "什么是进程？"}],
            "student_profile": {},
            "style": "standard",
        })

        assert state.get("sanity_error_code"), f"空回答必须触发 sanity 错误: {state}"
        assert not (state.get("response") or "").strip()

        # AutoCenter 收到 error 结果，payload 不含空 response 正文
        center = AutoCenter(tutor_agent=tutor)
        task = CenterTask(
            mode="auto", intent="tutor_question", input="什么是进程？",
            params={"question": "什么是进程？"},
            context={"messages": [{"role": "user", "content": "什么是进程？"}],
                     "student_profile": {}, "conversation_id": 7},
            sequence=0,
        )
        result = await center.execute(task)
        assert result.event_type == "error"
        assert "response" not in (result.payload or {})

    async def test_empty_assistant_in_history_not_sent_to_llm(self):
        """历史里的空 assistant 消息（旧数据）不得发给 LLM。"""
        llm = _FakeLLM(replies=["递归是函数调用自身的编程技巧。"])
        tutor = _make_tutor(llm)

        state = await tutor.run({
            "messages": [
                {"role": "user", "content": "什么是递归？"},
                {"role": "assistant", "content": ""},   # 旧脏数据
                {"role": "user", "content": "再举个例子？"},
            ],
            "student_profile": {},
            "style": "standard",
        })

        assert state.get("response")
        sent = llm.calls[-1]["messages"]
        assert all(str(m.get("content", "")).strip() for m in sent), \
            f"空消息被发给了 LLM: {sent}"

    async def test_no_history_standalone_question(self):
        """无历史旧调用保持兼容：单条消息照常回答。"""
        llm = _FakeLLM(replies=["递归是函数调用自身，需要有基线条件。"])
        tutor = _make_tutor(llm)

        state = await tutor.run({
            "messages": [{"role": "user", "content": "什么是递归？"}],
            "student_profile": {},
            "style": "standard",
        })

        assert state.get("response")
        sent = llm.calls[-1]["messages"]
        assert sent == [{"role": "user", "content": "什么是递归？"}]
