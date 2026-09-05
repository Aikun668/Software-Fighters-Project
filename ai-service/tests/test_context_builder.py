"""Tests for ContextBuilder: 按需上下文组装（对话底座救援 · Task 6）。

对应计划"失败测试先行"四条：
1. 当前问题"TCP 为什么需要三次握手？"能保留最近"我们在学 TCP/IP"。
2. 画像中的"偏好先直观后公式"可以保留；与问题无关的字段不得注入。
3. KB 中 TCP 建连片段可以保留；二叉树遍历片段不得注入。
4. 当前消息永远在最终用户位置。

本文件全部为离线纯逻辑测试：无 LLM、无网络。
"""

import pytest

from app.services.context_builder import BuiltContext, ContextBuilder


@pytest.fixture
def builder():
    return ContextBuilder()


@pytest.fixture
def tcp_history():
    return [
        {"role": "user", "content": "我们在学 TCP/IP"},
        {"role": "assistant", "content": "好的，TCP/IP 是互联网的核心协议族。"},
        {"role": "user", "content": "TCP 为什么需要三次握手？"},
    ]


class TestRecentTurnWindow:
    """最近窗口：完整轮次保留与切分"""

    def test_keeps_recent_topic_message(self, builder, tcp_history):
        """计划样例 1：最近的"我们在学 TCP/IP"必须保留在窗口里"""
        ctx = builder.build(
            system="你是学习助手",
            current_message="TCP 为什么需要三次握手？",
            history=tcp_history,
        )
        contents = [m["content"] for m in ctx.recent_turns]
        assert any("我们在学 TCP/IP" in c for c in contents)

    def test_window_never_starts_with_orphan_assistant(self, builder):
        """切分只发生在轮次边界：窗口不能以"回复在、提问被切掉"开头"""
        history = []
        for i in range(30):
            history.append({"role": "user", "content": f"问题{i}"})
            history.append({"role": "assistant", "content": f"回答{i}"})
        b = ContextBuilder(max_turns=4)
        ctx = b.build(system="s", current_message="当前问题", history=history)
        assert len(ctx.recent_turns) > 0
        assert ctx.recent_turns[0]["role"] == "user"
        assert ctx.recent_turns[0]["content"] == "问题26"

    def test_max_turns_respected(self, builder):
        history = []
        for i in range(20):
            history.append({"role": "user", "content": f"问题{i}"})
            history.append({"role": "assistant", "content": f"回答{i}"})
        b = ContextBuilder(max_turns=3)
        ctx = b.build(system="s", current_message="当前问题", history=history)
        users = [m for m in ctx.recent_turns if m["role"] == "user"]
        assert [u["content"] for u in users] == ["问题17", "问题18", "问题19"]

    def test_consecutive_user_messages_stay_together(self, builder):
        """连续多条 user（未获回复）归入同一轮次，不被拆散切断"""
        history = [
            {"role": "user", "content": "第一句"},
            {"role": "user", "content": "第二句"},
            {"role": "assistant", "content": "回答"},
        ]
        b = ContextBuilder(max_turns=1)
        ctx = b.build(system="s", current_message="当前问题", history=history)
        contents = [m["content"] for m in ctx.recent_turns]
        assert contents == ["第一句", "第二句", "回答"]

    def test_history_starting_with_assistant(self, builder):
        """历史以 assistant 前奏开头（如问候语）不报错，正常保留"""
        history = [
            {"role": "assistant", "content": "你好，有什么可以帮你？"},
            {"role": "user", "content": "讲讲进程"},
        ]
        ctx = builder.build(system="s", current_message="那线程呢？", history=history)
        assert ctx.recent_turns[0]["content"] == "你好，有什么可以帮你？"

    def test_non_dict_messages_skipped(self, builder):
        history = ["脏数据", {"role": "user", "content": "有效消息"}]
        ctx = builder.build(system="s", current_message="继续", history=history)
        assert [m["content"] for m in ctx.recent_turns] == ["有效消息"]

    def test_empty_history(self, builder):
        ctx = builder.build(system="s", current_message="什么是进程？", history=[])
        assert ctx.recent_turns == []


class TestProfileRelevance:
    """画像片段：按需注入，不全量 dump"""

    def test_plan_case_2_preference_kept_unrelated_dropped(self, builder, tcp_history):
        """计划样例 2：偏好保留，无关字段不注入"""
        profile = {
            "cognitive_style": "偏好先直观后公式",
            "interest_direction": ["摄影", "英语词汇"],
            "learning_goal": "通过软件设计师考试",
        }
        ctx = builder.build(
            system="s",
            current_message="TCP 为什么需要三次握手？",
            history=tcp_history,
            student_profile=profile,
        )
        joined = " ".join(ctx.profile_facts)
        assert "偏好先直观后公式" in joined
        assert "摄影" not in joined
        assert "软件设计师" not in joined

    def test_weak_point_with_topic_overlap_kept(self, builder, tcp_history):
        """薄弱点与当前话题相关时注入"""
        profile = {"weak_points": ["TCP 三次握手总是记不清"]}
        ctx = builder.build(
            system="s",
            current_message="TCP 为什么需要三次握手？",
            history=tcp_history,
            student_profile=profile,
        )
        assert any("TCP" in f for f in ctx.profile_facts)

    def test_empty_profile(self, builder):
        ctx = builder.build(system="s", current_message="问题", student_profile={})
        assert ctx.profile_facts == []

    def test_none_and_empty_values_skipped(self, builder):
        profile = {"cognitive_style": None, "interest_direction": [], "learning_goal": ""}
        ctx = builder.build(system="s", current_message="问题", student_profile=profile)
        assert ctx.profile_facts == []

    def test_profile_max_facts_cap(self, builder):
        profile = {
            "cognitive_style": "视觉型",
            "knowledge_base": 50,
            "learning_preference": "先看图",
            "teaching_style": "通俗",
        }
        b = ContextBuilder(profile_max_facts=2)
        ctx = b.build(system="s", current_message="问题", student_profile=profile)
        assert len(ctx.profile_facts) == 2


class TestKBRelevance:
    """知识库证据：相关保留，跑题丢弃"""

    TCP_CHUNK = {"content": "TCP 建连需要客户端与服务器交换三次握手报文，之后才进入数据传输。", "score": 0.8}
    TREE_CHUNK = {"content": "二叉树的遍历方式包括前序、中序和后序三种。", "score": 0.9}

    def test_plan_case_3_tcp_kept_tree_dropped(self, builder, tcp_history):
        """计划样例 3：TCP 建连片段保留，二叉树片段不得注入"""
        ctx = builder.build(
            system="s",
            current_message="TCP 为什么需要三次握手？",
            history=tcp_history,
            kb_candidates=[self.TCP_CHUNK, self.TREE_CHUNK],
        )
        assert len(ctx.kb_evidence) == 1
        assert "三次握手" in ctx.kb_evidence[0]

    def test_high_score_but_irrelevant_still_dropped(self, builder, tcp_history):
        """检索器给了高分但内容跑题的片段，同样不得注入"""
        ctx = builder.build(
            system="s",
            current_message="TCP 为什么需要三次握手？",
            history=tcp_history,
            kb_candidates=[self.TREE_CHUNK],
        )
        assert ctx.kb_evidence == []

    def test_low_score_dropped(self, builder, tcp_history):
        low = dict(self.TCP_CHUNK, score=0.1)
        ctx = builder.build(
            system="s",
            current_message="TCP 为什么需要三次握手？",
            history=tcp_history,
            kb_candidates=[low],
        )
        assert ctx.kb_evidence == []

    def test_sorted_by_score_desc(self, builder, tcp_history):
        other = {"content": "TCP 的拥塞控制依赖慢启动阈值。", "score": 0.5}
        ctx = builder.build(
            system="s",
            current_message="TCP 为什么需要三次握手？",
            history=tcp_history,
            kb_candidates=[other, self.TCP_CHUNK],
        )
        assert len(ctx.kb_evidence) == 2
        assert "三次握手" in ctx.kb_evidence[0]

    def test_top_k_cap(self, builder, tcp_history):
        chunks = [
            {"content": f"TCP 协议知识点{variant}包含建连细节", "score": 0.9}
            for variant in "甲乙丙丁"
        ]
        b = ContextBuilder(kb_top_k=2)
        ctx = b.build(
            system="s",
            current_message="TCP 为什么需要三次握手？",
            history=tcp_history,
            kb_candidates=chunks,
        )
        assert len(ctx.kb_evidence) == 2

    def test_followup_reference_resolves_via_recent_user_msgs(self, builder):
        """跨轮指代："那线程呢？"应借助最近 user 消息命中进程/线程相关片段"""
        history = [
            {"role": "user", "content": "我们在学操作系统的进程与线程"},
            {"role": "assistant", "content": "进程是资源分配的基本单位。"},
        ]
        kb_chunks = [
            {"content": "线程是 CPU 调度的基本单位，共享所属进程的资源。", "score": 0.7},
            {"content": "光合作用是植物将光能转化为化学能的过程。", "score": 0.6},
        ]
        ctx = builder.build(
            system="s",
            current_message="那线程呢？",
            history=history,
            kb_candidates=kb_chunks,
        )
        assert len(ctx.kb_evidence) == 1
        assert "线程" in ctx.kb_evidence[0]

    def test_empty_candidates(self, builder):
        ctx = builder.build(system="s", current_message="问题", kb_candidates=[])
        assert ctx.kb_evidence == []


class TestCurrentMessagePosition:
    """当前消息永远在最终用户位置"""

    def test_plan_case_4_last_message_is_current_user_message(self, builder, tcp_history):
        ctx = builder.build(
            system="s",
            current_message="TCP 为什么需要三次握手？",
            history=tcp_history,
        )
        msgs = ctx.messages()
        assert msgs[-1]["role"] == "user"
        assert msgs[-1]["content"] == "TCP 为什么需要三次握手？"

    def test_current_message_not_duplicated(self, builder, tcp_history):
        ctx = builder.build(
            system="s",
            current_message="TCP 为什么需要三次握手？",
            history=tcp_history,
        )
        msgs = ctx.messages()
        contents = [m["content"] for m in msgs]
        assert contents.count("TCP 为什么需要三次握手？") == 1

    def test_correction_overrides_old_topic(self, builder):
        """验收样例："不是，我说的是虚拟内存。"必须覆盖旧主题，处于最终 user 位置"""
        history = [
            {"role": "user", "content": "讲讲进程调度"},
            {"role": "assistant", "content": "进程调度有 FCFS、SJF、RR 等。"},
        ]
        ctx = builder.build(
            system="s",
            current_message="不是，我说的是虚拟内存。",
            history=history,
            summary="用户在学习进程调度",
        )
        msgs = ctx.messages()
        assert msgs[-1]["content"] == "不是，我说的是虚拟内存。"
        # 摘要原文不进入消息列表（摘要独立在 system 段），不会压过当前输入
        assert all("用户在学习进程调度" not in m["content"] for m in msgs)
        assert "用户在学习进程调度" in ctx.system_prompt()


class TestSummary:
    """摘要：缺失保持空，不杜撰"""

    def test_missing_summary_stays_empty(self, builder, tcp_history):
        ctx = builder.build(
            system="s",
            current_message="TCP 为什么需要三次握手？",
            history=tcp_history,
            summary=None,
        )
        assert ctx.summary == ""
        assert "对话历史摘要" not in ctx.system_prompt()

    def test_blank_summary_stays_empty(self, builder):
        ctx = builder.build(system="s", current_message="问题", summary="   ")
        assert ctx.summary == ""

    def test_summary_included_when_present(self, builder):
        ctx = builder.build(system="s", current_message="问题", summary="用户已理解 IP 与 MAC 的区别")
        assert ctx.summary == "用户已理解 IP 与 MAC 的区别"
        assert "用户已理解 IP 与 MAC 的区别" in ctx.system_prompt()


class TestSystemPromptAssembly:
    """系统提示按固定顺序组装，空段整体省略"""

    def test_fixed_section_order(self, builder):
        ctx = builder.build(
            system="稳定系统指令",
            current_message="TCP 为什么需要三次握手？",
            summary="早期摘要内容",
            student_profile={"cognitive_style": "偏好先直观后公式"},
            kb_candidates=[TestKBRelevance.TCP_CHUNK],
        )
        prompt = ctx.system_prompt()
        i_system = prompt.index("稳定系统指令")
        i_summary = prompt.index("对话历史摘要")
        i_profile = prompt.index("学生画像")
        i_kb = prompt.index("参考知识库内容")
        assert i_system < i_summary < i_profile < i_kb

    def test_empty_sections_omitted(self, builder):
        ctx = builder.build(system="稳定系统指令", current_message="问题")
        prompt = ctx.system_prompt()
        assert "对话历史摘要" not in prompt
        assert "学生画像" not in prompt
        assert "参考知识库内容" not in prompt
        assert prompt == "稳定系统指令"

    def test_system_never_none(self, builder):
        ctx = builder.build(system=None, current_message="问题")
        assert ctx.system == ""


class TestBuiltContextContract:
    """BuiltContext 数据契约"""

    def test_default_fields(self):
        ctx = BuiltContext(system="s")
        assert ctx.summary == ""
        assert ctx.recent_turns == []
        assert ctx.profile_facts == []
        assert ctx.kb_evidence == []
        assert ctx.current_message == ""

    def test_messages_returns_copies(self, builder, tcp_history):
        ctx = builder.build(system="s", current_message="问题", history=tcp_history)
        msgs = ctx.messages()
        msgs[0]["content"] = "篡改"
        assert ctx.recent_turns[0]["content"] != "篡改"
