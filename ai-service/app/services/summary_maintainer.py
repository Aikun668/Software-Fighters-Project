"""SummaryMaintainer — 对话摘要维护（对话底座救援 · Task 7）。

只回答两个问题：

1. 什么时候更新摘要？
   只有两个时机：对话轮次超出最近窗口（有旧轮次被"驱逐"），或一个主题结束
   （用户确认听懂，或明确换题/纠正——被替换的主题其讨论已经结束）。
   其余情况一律不动摘要。

2. 摘要里写什么？
   只保存四类事实：确认主题、已解决点、当前卡点、明确偏好；全部锚定用户原话
   （引用式记录）。绝不写系统推断的能力评价——"已掌握""成绩差"之类未经用户
   证实的话不写，assistant 的客套夸奖（"你掌握得很好"）也不算证据。
   提取规则是启发式的：提取不出就跳过，宁缺毋滥，不伪造。

摘要是状态记录：不伪造、不删改继承的旧文本（notes 原样保留）。被更正的旧主题
降级为"过往主题"，"当前主题"永远反映用户最近一次明确表态；当前输入不被摘要
压制由 ContextBuilder 保证（当前消息处于消息列表最后 user 位置）。

确定性纯逻辑：无 LLM、无 IO。与 TutorAgent / ChatCenter 的持久化接线在
Task 7 收尾阶段单独完成，本文件先独立交付并可单测。
"""

import logging
import re
from dataclasses import dataclass, field

from app.services.context_builder import group_turns

logger = logging.getLogger(__name__)

# 摘要各类目的容量上限（超出时丢弃最旧的）
MAX_PAST_TOPICS = 5
MAX_RESOLVED = 5
MAX_BLOCKERS = 3
MAX_PREFERENCES = 5

# 单条记录的长度上限（引用式记录，防止整段对话进摘要）
QUOTE_LIMIT = 40
TOPIC_LIMIT = 12

# ── 信号识别 ────────────────────────────────────────────────────

# 主题完成：用户确认听懂/解决
_COMPLETION_RE = re.compile(
    r"懂了|明白了|清楚了|理解了|解决了|学会了|搞定了|原来如此|这回懂|总算懂"
)
# 主题切换/纠正：旧主题的讨论被打断结束（计划失败测试场景）
_CORRECTION_RE = re.compile(
    r"不是[，,、\s]*我|不对[，,、\s]|我说错了|说错了|换(?:个|了)(?:话题|问题|主题)"
    r"|我想问的是|我要问的是|我说的是"
)
# 当前卡点
_BLOCKER_RE = re.compile(
    r"不会|不懂|搞不清|搞不清楚|搞不懂|弄不清|弄混|搞混|分不清|不理解|不明白|没懂|没搞懂"
    r"|听不懂|看不懂|卡在|很乱|有点乱|还是乱|一直没搞懂|记不清|记不住|混淆"
)
# 明确偏好
_PREFERENCE_RE = re.compile(
    r"我(?:喜欢|偏好|习惯|更想|希望|想要)|请(?:用|举|给我)|举个例子|举生活例子"
    r"|讲(?:得)?简单(?:一)?点|简单一点|通俗(?:一)?点|慢(?:一)?点|细(?:一)?点"
    r"|(?:用|举)(?:中文|英文|英语|生活)(?:的)?例子|画(?:张|个)图(?:给)?我"
)

# 主题提取：从用户原话中截取"在学/在问"的宾语
_TOPIC_CORRECTION_RE = re.compile(
    r"(?:说的是|问的是|想问的是|想说的是)([\u4e00-\u9fffA-Za-z0-9+#/]{2,})"
)
_TOPIC_ASK_RE = re.compile(
    r"(?:^|[，,、\s])(?:我)?(?:现在|刚刚)?(?:想)?问[\s]*([\u4e00-\u9fffA-Za-z0-9+#/]{2,})"
)
_TOPIC_LEARN_RE = re.compile(
    r"(?:在学|在学习|正在学|最近在学|学的是|自学|学一下|在研究|在复习|学)[\s]*"
    r"([\u4e00-\u9fffA-Za-z0-9+#/]{2,})"
)
# 话题尾部问句套话/确认语，逐个剥离
_TOPIC_TAILS = [
    "有什么区别", "是怎么回事", "怎么理解", "怎么解决", "明白了吗", "清楚了吗",
    "理解了吗", "学会了吗", "的区别", "是什么", "怎么样", "怎么办", "为什么",
    "明白了", "懂了吗", "懂了", "清楚了", "理解了", "学会了", "的本质",
    "的概念", "的原理", "的细节", "搞懂了", "弄懂了", "搞懂", "弄懂",
    "明白", "清楚", "理解",
]
# 话题首尾语气填充词
_EDGE_CHARS = "那再就这哪了个是的说讲一下下呢吗啊吧呀哦噢嘛我你他她它咱"
# 兜底提取出的"主题"若是这些泛泛之词，视为无主题（宁缺毋滥）
_VAGUE_TOPICS = {
    "继续", "然后", "接着", "还是", "另外", "对了", "好的", "好吧",
    "嗯", "嗯嗯", "谢谢", "请问", "ok", "okay", "明白", "清楚",
    "理解", "懂了", "会了", "解决", "搞定", "学会了",
    "什么", "怎么", "如何", "哪些", "哪个", "为啥",
    "随便", "随便聊聊", "聊聊", "随便看看",
}
_ASCII_TERM_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#\-]*")


@dataclass
class SummaryState:
    """结构化对话摘要：只含四类事实 + 继承的旧摘要文本。"""

    current_topic: str = ""        # 当前主题（用户最近一次明确表态）
    past_topics: list[str] = field(default_factory=list)   # 过往确认主题（旧→新）
    resolved: list[str] = field(default_factory=list)      # 已解决点
    blockers: list[str] = field(default_factory=list)      # 当前卡点
    preferences: list[str] = field(default_factory=list)   # 明确偏好
    notes: str = ""                # 继承的旧摘要文本：不解析、不丢弃、不伪造

    def to_text(self) -> str:
        """按"当前优先"的顺序压平为文本，可直接交给 ContextBuilder 的 summary。"""
        sections = []
        if self.current_topic:
            sections.append(f"当前主题：{self.current_topic}")
        if self.past_topics:
            sections.append("已确认主题：" + "、".join(self.past_topics))
        if self.resolved:
            sections.append("已解决：" + "；".join(self.resolved))
        if self.blockers:
            sections.append("当前卡点：" + "；".join(self.blockers))
        if self.preferences:
            sections.append("用户偏好：" + "；".join(self.preferences))
        if self.notes:
            sections.append("早期记录：" + self.notes)
        return "\n".join(sections)


class SummaryMaintainer:
    """维护对话摘要。update()/should_update() 为纯函数，无 IO、无 LLM。"""

    def __init__(self, max_turns: int = 8):
        self.max_turns = max(1, max_turns)

    # ── 更新时机 ────────────────────────────────────────────────

    def should_update(self, history: list[dict] | None, current_message: str = "") -> bool:
        """仅两种时机更新：轮次超出最近窗口，或最近一条用户消息结束了一个主题。

        history 不含当前消息（与 ContextBuilder 同契约）。
        纠正/换题视为"一个主题结束"：被替换主题的讨论已经结束，
        这是让"旧摘要不压过当前纠正"成立的最小解释。
        """
        turns = group_turns(history or [])
        if len(turns) > self.max_turns:
            return True
        for text in self._latest_user_signals(history, current_message):
            if _COMPLETION_RE.search(text) or _CORRECTION_RE.search(text):
                return True
        return False

    def update(
        self,
        summary: "SummaryState | str | None" = None,
        history: list[dict] | None = None,
        current_message: str = "",
    ) -> SummaryState:
        """把被驱逐的旧轮次与当前消息信号合并进摘要，返回新的 SummaryState。

        输入的 summary 可以是 SummaryState（会话里已维护的结构化摘要）、
        str（历史遗留的纯文本摘要，原样存入 notes）或 None。
        输入不会被修改，总是返回新对象。
        """
        state = self._copy_state(summary)
        turns = group_turns(history or [])
        evicted = turns[: -self.max_turns] if len(turns) > self.max_turns else []
        for turn in evicted:
            for msg in turn:
                if msg.get("role") == "user":
                    self._apply_message(state, str(msg.get("content", "")))
        if current_message:
            self._apply_message(state, current_message)
        return state

    # ── 事实提取与应用 ──────────────────────────────────────────

    def _apply_message(self, state: SummaryState, text: str) -> None:
        """把一条用户消息中的信号合并进摘要。纠正 > 完成 > 卡点/偏好/主题。"""
        text = text.strip()
        if not text:
            return

        if _CORRECTION_RE.search(text):
            new_topic = self._extract_topic(text)
            if new_topic:
                if state.current_topic and state.current_topic != new_topic:
                    self._push(state.past_topics, state.current_topic, MAX_PAST_TOPICS)
                    # 被更正的主题不再是卡点
                    state.blockers = [
                        b for b in state.blockers if not self._same_subject(b, state.current_topic)
                    ]
                state.current_topic = new_topic
            return

        if _COMPLETION_RE.search(text):
            topic = state.current_topic or self._extract_topic(text)
            if topic:
                self._push(state.resolved, topic, MAX_RESOLVED)
                state.blockers = [
                    b for b in state.blockers if not self._same_subject(b, topic)
                ]
                if state.current_topic and self._same_subject(state.current_topic, topic):
                    state.current_topic = ""
            return

        has_preference = bool(_PREFERENCE_RE.search(text))

        if _BLOCKER_RE.search(text):
            blocker = self._extract_topic(text) or self._quote(text)
            if blocker:
                self._push(state.blockers, blocker, MAX_BLOCKERS)

        if has_preference:
            preference = self._quote_sentence(text)
            if preference:
                self._push(state.preferences, preference, MAX_PREFERENCES)

        # 偏好陈述不是主题陈述，不从这类消息里提取当前主题
        if not has_preference:
            topic = self._extract_topic(text)
            if topic and topic != state.current_topic:
                if state.current_topic:
                    self._push(state.past_topics, state.current_topic, MAX_PAST_TOPICS)
                state.current_topic = topic

    # ── 主题提取（启发式，锚定原话） ────────────────────────────

    @classmethod
    def _extract_topic(cls, text: str) -> str:
        """提取用户话中的主题短语；提取不出/泛泛之词返回空串，绝不杜撰。"""
        ascii_terms = _ASCII_TERM_RE.findall(text)

        for pattern in (_TOPIC_CORRECTION_RE, _TOPIC_ASK_RE, _TOPIC_LEARN_RE):
            m = pattern.search(text)
            if m:
                topic = cls._validated(cls._strip_edges(m.group(1)))
                if topic:
                    if ascii_terms and not re.search(r"[A-Za-z]", topic):
                        topic = f"{ascii_terms[0]} {topic}"
                    return topic[:TOPIC_LIMIT]

        # 兜底：最长 CJK 连续段（剥掉问句套话后），作为引用式主题
        runs = re.findall(r"[\u4e00-\u9fff]{2,}", text)
        topic = cls._validated(cls._strip_edges(cls._strip_tails(max(runs, key=len)))) if runs else ""
        if not topic and ascii_terms:
            return " ".join(ascii_terms[:2])[:TOPIC_LIMIT]
        if topic and ascii_terms and not re.search(r"[A-Za-z]", topic):
            topic = f"{ascii_terms[0]} {topic}"
        return topic[:TOPIC_LIMIT]

    @staticmethod
    def _validated(topic: str) -> str:
        """泛泛之词、过短碎片不算主题。"""
        if not topic or len(topic) < 2:
            return ""
        if topic.lower() in _VAGUE_TOPICS:
            return ""
        return topic

    @staticmethod
    def _strip_tails(text: str) -> str:
        changed = True
        while changed:
            changed = False
            for tail in _TOPIC_TAILS:
                if text.endswith(tail) and len(text) > len(tail):
                    text = text[: -len(tail)]
                    changed = True
        return text

    @staticmethod
    def _strip_edges(text: str) -> str:
        return text.strip(_EDGE_CHARS + " ").strip()

    @staticmethod
    def _quote(text: str) -> str:
        """压缩为引用式短句。"""
        return re.sub(r"\s+", " ", text).strip()[:QUOTE_LIMIT]

    @classmethod
    def _quote_sentence(cls, text: str) -> str:
        """取包含偏好信号的那一句话（引用式记录）。"""
        for sentence in re.split(r"[。？！?!;；\n]", text):
            if _PREFERENCE_RE.search(sentence):
                return cls._quote(sentence)
        return cls._quote(text)

    # ── 工具 ────────────────────────────────────────────────────

    @staticmethod
    def _push(lst: list[str], item: str, cap: int) -> None:
        if not item:
            return
        if item in lst:
            return
        lst.append(item)
        if len(lst) > cap:
            del lst[: len(lst) - cap]

    @staticmethod
    def _same_subject(a: str, b: str) -> bool:
        """两条记录是否指同一主题：相等或互为子串（"三次握手" vs "TCP 三次握手"）。"""
        if not a or not b:
            return False
        return a == b or a in b or b in a

    @staticmethod
    def _latest_user_signals(history: list[dict] | None, current_message: str) -> list[str]:
        texts = []
        if current_message:
            texts.append(current_message)
        for msg in reversed(history or []):
            if isinstance(msg, dict) and msg.get("role") == "user":
                texts.append(str(msg.get("content", "")))
                break
        return texts

    @staticmethod
    def _copy_state(summary: "SummaryState | str | None") -> SummaryState:
        if summary is None:
            return SummaryState()
        if isinstance(summary, SummaryState):
            return SummaryState(
                current_topic=summary.current_topic,
                past_topics=list(summary.past_topics),
                resolved=list(summary.resolved),
                blockers=list(summary.blockers),
                preferences=list(summary.preferences),
                notes=summary.notes,
            )
        return SummaryState(notes=str(summary).strip())
