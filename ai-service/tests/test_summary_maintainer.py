"""Tests for SummaryMaintainer: 对话摘要维护（对话底座救援 · Task 7）。

对应计划步骤：
1. 失败测试：旧摘要写"用户在学习进程调度"时，当前"不是，我现在问虚拟内存"必须优先。
2. 对话超过最近窗口或一个主题完成时才更新摘要。
3. 摘要仅保存确认主题、已解决点、当前卡点、明确偏好；不得写未经证实的能力评价。
4. 验收：长对话仍能记住主题，但不压制当前输入。

本文件全部为离线纯逻辑测试：无 LLM、无网络。
"""

import pytest

from app.services.context_builder import ContextBuilder
from app.services.summary_maintainer import (
    MAX_BLOCKERS,
    MAX_PAST_TOPICS,
    SummaryMaintainer,
    SummaryState,
)


@pytest.fixture
def maintainer():
    return SummaryMaintainer(max_turns=4)


def _turns(count, user_text="继续", assistant_text="好的。"):
    history = []
    for _ in range(count):
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": assistant_text})
    return history


class TestUpdateTiming:
    """更新时机：只有窗口溢出或主题结束才动摘要"""

    def test_no_update_within_window_without_signals(self, maintainer):
        history = _turns(2)
        assert not maintainer.should_update(history, current_message="谢谢")
        state = maintainer.update(None, history, "谢谢")
        assert state.to_text() == ""

    def test_update_when_window_overflow(self, maintainer):
        history = [{"role": "user", "content": "我们在学操作系统的进程管理"}]
        history += [{"role": "assistant", "content": "好的。"}]
        history += _turns(5)  # 共 6 轮 > max_turns=4，第一轮被驱逐
        assert maintainer.should_update(history)
        state = maintainer.update(None, history)
        assert "进程管理" in state.to_text()

    def test_update_on_completion_signal(self, maintainer):
        history = [
            {"role": "user", "content": "讲讲TCP三次握手"},
            {"role": "assistant", "content": "三次握手是……"},
        ]
        assert maintainer.should_update(history, current_message="懂了，明白了！")

    def test_update_on_correction(self, maintainer):
        history = _turns(2)
        assert maintainer.should_update(history, current_message="不是，我现在问虚拟内存")

    def test_correction_in_last_history_message_counts(self, maintainer):
        history = _turns(1)
        history.append({"role": "user", "content": "不对，我说的是虚拟内存"})
        assert maintainer.should_update(history)


class TestCorrectionPriority:
    """计划失败测试：旧摘要不得压过当前纠正"""

    PLAN_HISTORY = [
        {"role": "user", "content": "讲讲进程调度"},
        {"role": "assistant", "content": "进程调度有 FCFS、SJF、RR 等。"},
        {"role": "user", "content": "进程和线程的区别呢"},
        {"role": "assistant", "content": "进程是资源分配单位，线程是调度单位。"},
    ]

    def test_plan_case_current_input_wins(self, maintainer):
        """旧摘要"用户在学习进程调度" + 当前"不是，我现在问虚拟内存" → 当前优先"""
        state = maintainer.update(
            "用户在学习进程调度",
            self.PLAN_HISTORY,
            "不是，我现在问虚拟内存",
        )
        text = state.to_text()
        assert "当前主题：虚拟内存" in text
        # 当前主题排在继承的旧记录之前
        assert text.index("当前主题：虚拟内存") < text.index("用户在学习进程调度")

    def test_plan_case_end_to_end_with_context_builder(self, maintainer):
        """与 ContextBuilder 集成：纠正后的摘要在 system 段，当前消息仍在最后"""
        state = maintainer.update(
            "用户在学习进程调度",
            self.PLAN_HISTORY,
            "不是，我现在问虚拟内存",
        )
        ctx = ContextBuilder(max_turns=4).build(
            system="你是学习助手",
            current_message="不是，我现在问虚拟内存",
            history=self.PLAN_HISTORY,
            summary=state.to_text(),
        )
        assert ctx.messages()[-1]["role"] == "user"
        assert ctx.messages()[-1]["content"] == "不是，我现在问虚拟内存"
        assert "虚拟内存" in ctx.system_prompt()
        # 旧摘要只存在于 system 段，不进入消息列表压过当前输入
        assert "用户在学习进程调度" in ctx.system_prompt()
        assert all("用户在学习进程调度" not in m["content"] for m in ctx.messages())

    def test_structured_current_topic_demoted_to_past(self, maintainer):
        state = maintainer.update(
            SummaryState(current_topic="进程调度"),
            [],
            "不是，我说的是虚拟内存",
        )
        assert state.current_topic == "虚拟内存"
        assert "进程调度" in state.past_topics


class TestSummaryContentRules:
    """摘要只保存四类事实，不写未经证实的能力评价"""

    ALLOWED_PREFIXES = ("当前主题：", "已确认主题：", "已解决：", "当前卡点：", "用户偏好：", "早期记录：")

    def test_only_allowed_sections(self, maintainer):
        history = [
            {"role": "user", "content": "我们在学操作系统的进程管理"},
            {"role": "assistant", "content": "好。"},
            {"role": "user", "content": "进程和线程老是搞混"},
            {"role": "assistant", "content": "区别在于……"},
        ] + _turns(4)
        state = maintainer.update("用户偏好举例子", history)
        for line in state.to_text().splitlines():
            assert line.startswith(self.ALLOWED_PREFIXES), line

    def test_assistant_praise_not_recorded(self, maintainer):
        """assistant 的客套夸奖不是证据，不得进入摘要"""
        history = [
            {"role": "user", "content": "讲讲TCP"},
            {"role": "assistant", "content": "你已经完全掌握了TCP！你太聪明了！"},
        ] + _turns(4)
        state = maintainer.update(None, history)
        assert "掌握" not in state.to_text()
        assert "聪明" not in state.to_text()

    def test_no_unverified_evaluation_from_vague_question(self, maintainer):
        """用户问"我学得怎么样"也不构成能力评价"""
        history = _turns(5)
        state = maintainer.update(None, history, "我学得怎么样？")
        text = state.to_text()
        for banned in ("掌握", "成绩", "水平很差", "学得很好"):
            assert banned not in text

    def test_user_confirmed_completion_recorded(self, maintainer):
        """真实两步流：先"讲讲TCP三次握手"建立当前主题，再确认听懂 → 移入已解决"""
        state = maintainer.update(None, [], "讲讲TCP三次握手")
        assert state.current_topic == "TCP 三次握手"
        state = maintainer.update(state, [], "懂了，明白了！")
        assert state.resolved and "三次握手" in state.resolved[0]
        assert state.current_topic == ""

    def test_blocker_recorded_from_user_words(self, maintainer):
        history = _turns(5)
        state = maintainer.update(None, history, "进程和线程我老是搞混")
        assert state.blockers
        assert "进程" in state.blockers[-1] or "线程" in state.blockers[-1]

    def test_preference_recorded_as_quote(self, maintainer):
        history = _turns(5)
        state = maintainer.update(None, history, "我喜欢先举生活例子再讲公式")
        assert state.preferences
        assert "例子" in state.preferences[-1]
        # 偏好陈述不改变当前主题
        assert state.current_topic == ""

    def test_resolved_clears_matching_blocker(self, maintainer):
        state = SummaryState(current_topic="三次握手", blockers=["三次握手"])
        result = maintainer.update(state, [], "懂了，明白了！")
        assert result.blockers == []
        assert "三次握手" in result.resolved

    def test_caps_keep_most_recent(self, maintainer):
        state = SummaryState()
        topics = ["数据结构", "操作系统", "计算机网络", "数据库", "编译原理", "机器学习", "密码学", "图形学"]
        for t in topics:
            state = maintainer.update(state, [], f"现在在学{t}")
        assert state.current_topic == "图形学"
        assert len(state.past_topics) == MAX_PAST_TOPICS
        assert "数据结构" not in state.past_topics  # 最旧的被挤出
        assert "密码学" in state.past_topics

    def test_dedupe(self, maintainer):
        state = maintainer.update(None, [], "现在在学操作系统")
        again = maintainer.update(state, [], "现在在学操作系统")
        assert again.past_topics.count("操作系统") <= 1
        assert again.current_topic == "操作系统"

    def test_inputs_not_mutated(self, maintainer):
        original = SummaryState(current_topic="进程调度", blockers=["三次握手"])
        snapshot = original.to_text()
        maintainer.update(original, [], "不是，我说的是虚拟内存")
        assert original.to_text() == snapshot


class TestTopicExtraction:
    """主题提取启发式"""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("我们在学 TCP/IP", "TCP/IP"),
            ("不是，我说的是虚拟内存", "虚拟内存"),
            ("不是，我现在问虚拟内存", "虚拟内存"),
            ("进程和线程有什么区别", "进程和线程"),
            ("请问TCP是什么", "TCP"),
        ],
    )
    def test_extraction(self, maintainer, text, expected):
        assert maintainer._extract_topic(text) == expected

    @pytest.mark.parametrize(
        "text",
        ["谢谢", "继续", "明白了，谢谢！", "好的", "嗯嗯"],
    )
    def test_vague_messages_yield_no_topic(self, maintainer, text):
        assert maintainer._extract_topic(text) == ""


class TestLongConversation:
    """验收：长对话仍能记住主题，但不压制当前输入"""

    def test_long_conversation_retains_topic(self, maintainer):
        history = [{"role": "user", "content": "我们在学操作系统的进程管理"},
                   {"role": "assistant", "content": "好的，进程管理包括……"}]
        history += _turns(10)  # 远超 max_turns=4
        assert maintainer.should_update(history)
        state = maintainer.update(None, history)
        assert "进程管理" in state.to_text()

    def test_summary_does_not_suppress_current_input(self, maintainer):
        history = [{"role": "user", "content": "我们在学操作系统的进程管理"},
                   {"role": "assistant", "content": "好的。"}]
        history += _turns(10)
        state = maintainer.update(None, history)
        current = "不是，我现在问的是虚拟内存的分页机制"
        ctx = ContextBuilder(max_turns=4).build(
            system="你是学习助手",
            current_message=current,
            history=history,
            summary=state.to_text(),
        )
        assert ctx.messages()[-1]["content"] == current
        assert ctx.messages()[-1]["role"] == "user"
        assert "进程管理" in ctx.system_prompt()
