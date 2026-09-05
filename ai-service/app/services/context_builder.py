"""ContextBuilder — 按需组装模型上下文（对话底座救援 · Task 6）。

只做一件事：把"该进本轮 Prompt 的信息"按固定顺序挑出来、拼出来。

固定顺序（设计文档）：
    稳定系统指令 → 早期对话摘要 → 最近完整轮次 → 相关画像片段 → 相关知识库证据 → 当前用户消息

原则：
- 画像不是"每轮必传的背景档案"：只有会改变本轮回答的字段才注入，拿不准就不注入。
- 知识库证据必须与当前话题相关，不相关时为空；宁缺毋滥。
- 最近窗口按完整轮次切分，绝不切断一问一答。
- 摘要缺失时保持空，不临时杜撰；摘要是状态记录，不压过当前输入。
- 当前用户消息永远位于最终消息列表的最后一个 user 位置。

本模块为确定性纯逻辑：无 LLM 调用、无 IO、无网络。
与 TutorAgent 的接线（TutorAgent 只接收 BuiltContext）在 Task 6 收尾阶段单独完成，
本文件先独立交付并可单测。
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 最近窗口：保留最近 max_turns 个完整轮次（一轮 = 一条 user + 其后的 assistant 回复）
DEFAULT_MAX_TURNS = 8
# 相关性判断时回看的最近 user 消息数（解决"那线程呢？"这类跨轮指代）
RECALL_USER_TURNS = 3
# 知识库证据默认注入上限与最低分（score 存在时才检查分数）
DEFAULT_KB_TOP_K = 3
DEFAULT_KB_MIN_SCORE = 0.3
# 画像片段注入上限
DEFAULT_PROFILE_MAX_FACTS = 4

# 与 base_agent._format_profile 保持一致的中文标签（本地副本，避免引入 LLM 依赖）
_PROFILE_LABELS = {
    "knowledge_base": "知识基础",
    "cognitive_style": "学习风格",
    "learning_goal": "学习目标",
    "weak_points": "薄弱环节",
    "learning_pace": "学习节奏",
    "interest_direction": "兴趣方向",
}

# 答案塑形字段：无论当前问什么都会改变讲解方式/难度，允许直接注入
_ANSWER_SHAPING_KEYS = {"cognitive_style", "knowledge_base"}
# 答案塑形键名模式（兼容未枚举的偏好/风格类字段）
_ANSWER_SHAPING_KEY_RE = re.compile(r"style|preference|偏好|风格|水平|基础", re.IGNORECASE)

# 停用词：出现在任何句子里的高频虚词/通用词，不构成相关性证据
_STOPWORDS = {
    "什么", "怎么", "为什么", "如何", "可以", "就是", "这个", "那个", "哪些",
    "我们", "你们", "他们", "一下", "一些", "有点", "感觉", "觉得", "还是",
    "还有", "但是", "如果", "因为", "所以", "应该", "可能", "需要", "时候",
    "现在", "已经", "一个", "一下", "说说", "讲讲", "解释", "介绍", "明白",
    "理解", "知道", "简单", "详细", "例子", "举例", "问题", "帮助",
}


def group_turns(history: list[dict]) -> list[list[dict]]:
    """把消息序列按完整轮次分组（ContextBuilder 与 SummaryMaintainer 共用）。

    轮次定义：一条 user 消息（或连续多条未获回复的 user 消息）+ 其后的 assistant 回复。
    历史开头的孤立 assistant 消息（无对应用户提问）自成前奏轮次，不单独截断。
    切分只发生在轮次边界，因此窗口不会出现"回复在窗口里、提问被切掉"的半轮。
    非 dict 消息安全跳过。
    """
    turns: list[list[dict]] = []
    for msg in history:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        last_role = turns[-1][-1].get("role") if turns else None
        if not turns or (role == "user" and last_role != "user"):
            turns.append([msg])
        else:
            turns[-1].append(msg)
    return turns


def select_recent_turns(history: list[dict], max_turns: int) -> list[dict]:
    """取最近 max_turns 个完整轮次，摊平为消息列表。"""
    if max_turns <= 0:
        return []
    window = group_turns(history)[-max_turns:]
    return [dict(m) for turn in window for m in turn]


@dataclass
class BuiltContext:
    """ContextBuilder 的产物：交给 TutorAgent 的最小相关上下文。"""

    system: str                                   # 稳定系统指令（不随轮次变化）
    summary: str = ""                             # 早期对话摘要；缺失保持 ""
    recent_turns: list[dict] = field(default_factory=list)   # [{role, content}, ...] 完整轮次
    profile_facts: list[str] = field(default_factory=list)   # ["学习风格: ...", ...]
    kb_evidence: list[str] = field(default_factory=list)     # 相关知识库片段原文
    current_message: str = ""                     # 当前用户消息

    def messages(self) -> list[dict]:
        """组装 LLM 消息列表：最近轮次 + 当前消息（最后一个 user 位置）。"""
        msgs = [dict(m) for m in self.recent_turns if isinstance(m, dict)]
        msgs.append({"role": "user", "content": self.current_message})
        return msgs

    def system_prompt(self) -> str:
        """组装系统提示：system → 摘要 → 相关画像 → 相关知识库，空段整体省略。"""
        sections = [self.system.strip()]
        if self.summary:
            sections.append(
                "## 对话历史摘要（经过压缩的早期对话记录）\n" + self.summary.strip() + "\n---"
            )
        if self.profile_facts:
            lines = ["## 学生画像（仅保留与当前问题相关的信息）"]
            lines.extend(f"  - {fact}" for fact in self.profile_facts)
            sections.append("\n".join(lines))
        if self.kb_evidence:
            lines = ["## 参考知识库内容"]
            lines.extend(f"[{i}] {doc}" for i, doc in enumerate(self.kb_evidence, 1))
            sections.append("\n".join(lines))
        return "\n\n".join(s for s in sections if s)


class ContextBuilder:
    """按固定顺序构建 BuiltContext。build() 为纯函数，无 IO、无 LLM。"""

    def __init__(
        self,
        max_turns: int = DEFAULT_MAX_TURNS,
        kb_top_k: int = DEFAULT_KB_TOP_K,
        kb_min_score: float = DEFAULT_KB_MIN_SCORE,
        profile_max_facts: int = DEFAULT_PROFILE_MAX_FACTS,
    ):
        self.max_turns = max(1, max_turns)
        self.kb_top_k = max(0, kb_top_k)
        self.kb_min_score = kb_min_score
        self.profile_max_facts = max(0, profile_max_facts)

    def build(
        self,
        system: str,
        current_message: str,
        history: list[dict] | None = None,
        summary: str | None = None,
        student_profile: dict | None = None,
        kb_candidates: list[dict] | None = None,
    ) -> BuiltContext:
        """history 为过往消息（不含当前消息）。

        兼容把当前消息附在 history 末尾的调用方：末尾与 current_message
        完全相同的 user 消息会被识别并去重，避免当前问题在 Prompt 里出现两次。
        """
        history = list(history or [])
        if history and current_message:
            last = history[-1]
            if (
                isinstance(last, dict)
                and last.get("role") == "user"
                and str(last.get("content", "")) == str(current_message)
            ):
                history = history[:-1]
        recent_turns = select_recent_turns(history, self.max_turns)
        query = self._build_relevance_query(current_message, recent_turns)
        return BuiltContext(
            system=system or "",
            summary=self._clean_summary(summary),
            recent_turns=recent_turns,
            profile_facts=self._select_profile_facts(student_profile, query),
            kb_evidence=self._select_kb_evidence(kb_candidates, query),
            current_message=current_message or "",
        )

    # ── 相关性判断 ──────────────────────────────────────────────

    def _build_relevance_query(self, current_message: str, recent_turns: list[dict]) -> str:
        """相关性判断依据：当前消息 + 最近几条 user 消息（承接"那线程呢？"）。"""
        parts = [current_message or ""]
        user_msgs = [
            m.get("content", "")
            for m in reversed(recent_turns)
            if isinstance(m, dict) and m.get("role") == "user"
        ]
        parts.extend(user_msgs[:RECALL_USER_TURNS])
        return " ".join(p for p in parts if p)

    @staticmethod
    def _extract_terms(text: str) -> set[str]:
        """提取可比对的特征词：ASCII 词（TCP/CNN）+ 中文相邻二元组。"""
        if not text:
            return set()
        terms: set[str] = set()
        for word in re.findall(r"[A-Za-z][A-Za-z0-9+#\-]*", text):
            terms.add(word.lower())
        for run in re.findall(r"[\u4e00-\u9fff]{2,}", text):
            for i in range(len(run) - 1):
                bigram = run[i:i + 2]
                if bigram not in _STOPWORDS:
                    terms.add(bigram)
        return terms

    def _is_relevant(self, text: str, query_terms: set[str]) -> bool:
        if not query_terms:
            return False
        return bool(self._extract_terms(text) & query_terms)

    # ── 画像片段选择 ────────────────────────────────────────────

    def _select_profile_facts(self, profile: dict | None, query: str) -> list[str]:
        """只保留会改变本轮回答的画像字段。

        规则：
        - 答案塑形字段（风格/基础/偏好类）：只要非空就注入——它们对任何问题都生效。
        - 其余字段（目标/兴趣/节奏/薄弱点等）：必须与当前话题有词面交集才注入。
        """
        if not profile or not isinstance(profile, dict):
            return []
        query_terms = self._extract_terms(query)
        facts: list[str] = []
        for key, value in profile.items():
            if value is None or value == [] or value == "":
                continue
            text = "、".join(str(v) for v in value) if isinstance(value, list) else str(value)
            if not text.strip():
                continue
            is_shaping = key in _ANSWER_SHAPING_KEYS or _ANSWER_SHAPING_KEY_RE.search(key)
            if not is_shaping and not self._is_relevant(text, query_terms):
                continue
            label = _PROFILE_LABELS.get(key, key)
            facts.append(f"{label}: {text}")
            if len(facts) >= self.profile_max_facts:
                break
        return facts

    # ── 知识库证据选择 ──────────────────────────────────────────

    def _select_kb_evidence(self, candidates: list[dict] | None, query: str) -> list[str]:
        """只保留与当前话题相关的知识库片段；不相关时返回空。

        每个候选：{"content": str, "score": float | None}。
        - score 存在时必须 ≥ kb_min_score；
        - 同时要求与 query 有词面交集（拦住"检索器给了高分但内容跑题"的片段）；
        - 有分数时按分数降序，无分数保持原顺序；最多 kb_top_k 条。
        """
        if not candidates:
            return []
        query_terms = self._extract_terms(query)
        scored: list[tuple[float | None, int, str]] = []
        for i, cand in enumerate(candidates):
            if not isinstance(cand, dict):
                continue
            content = cand.get("content", "")
            if not content or not str(content).strip():
                continue
            content = str(content)
            score = cand.get("score")
            if score is not None and float(score) < self.kb_min_score:
                continue
            if not self._is_relevant(content, query_terms):
                continue
            scored.append((float(score) if score is not None else None, i, content))
        scored.sort(key=lambda t: (-(t[0] if t[0] is not None else -1.0), t[1]))
        return [content for _, _, content in scored[: self.kb_top_k]]

    # ── 摘要 ────────────────────────────────────────────────────

    @staticmethod
    def _clean_summary(summary: str | None) -> str:
        """摘要缺失时保持空，不临时杜撰。"""
        if not summary:
            return ""
        return str(summary).strip()
