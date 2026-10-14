"""CapabilityGate — 一级路由守门员（对话底座救援 · Task 4）。

只回答一个问题：这条输入是否明确要求一个专用产物或专用工作流？

一级结果固定为 NORMAL_CHAT / PLAN / RESOURCE / EXERCISE / VISUALIZATION，
默认值永远是 NORMAL_CHAT。放行能力必须同时满足"明确动词 + 明确产物"；
单个名词、模糊诉求、概念解释、举例请求一律回落 NORMAL_CHAT。

旧的 IntentRegistry / IntentExtractor 降级为能力路径内部的二级路由
（RouterAgent 关键词路由），不再决定一级路径。

确定性规则、无 LLM 调用；路由不确定时必须 NORMAL_CHAT。

【决策所有权】一级请求级分发 —— 本模块是唯一拥有者。
  - 唯一调用点：`ChatCenter.route`（`app/centers/chat_center.py`）
  - 输入：用户原始输入；输出：`CapabilityKind`
  - 禁止：在此选择 Center / Agent；禁止决定「进哪个业务域」（属二级 `RouterAgent`）
  - 约定：`temp_file/9.15工程改造计划/0、产品方向与约束/三类决策与命名约定.md`
"""

import re
from dataclasses import dataclass
from enum import Enum

from app.services.capability_map import MODE_TO_KIND


class CapabilityKind(str, Enum):
    NORMAL_CHAT = "NORMAL_CHAT"
    PLAN = "PLAN"
    RESOURCE = "RESOURCE"
    EXERCISE = "EXERCISE"
    VISUALIZATION = "VISUALIZATION"


@dataclass
class CapabilityDecision:
    kind: CapabilityKind
    reason: str
    confidence: float


# 显式 mode（非 auto）→ 能力类型：用户点了功能入口，直接放行
_MODE_TO_KIND: dict[str, CapabilityKind] = {
    mode: CapabilityKind(kind) for mode, kind in MODE_TO_KIND.items()
}

_CAPABILITY_CONFIDENCE = 0.75
_NORMAL_CONFIDENCE = 0.5
_EXPLICIT_MODE_CONFIDENCE = 1.0

# 疑问/解释句式：出现时按"概念解释或追问"理解，压过能力证据；
# 但带真实祈使（帮我/给我/请…）的生成请求不受影响。
_QUESTION_RE = re.compile(
    r"什么|为什么|怎么|如何|是什么|何为|吗|呢|\?|？"
    r"|讲讲|讲解|解释|介绍一下|说说|区别"
)
_IMPERATIVE_RE = re.compile(r"帮我|给我|请|麻烦|劳驾")

# 生成动词后紧跟"了/过"是陈述过去，不是请求生成（"做了5道题都错了"）
_NO_PAST = r"(?![了过])"

# 产物前的连接填充（"出 5 道进程调度选择题"里的"进程调度"）
_FILL = r"[^。？！?!;；\n]{0,%d}"

# 显式能力证据：动词 + 产物成对出现才算数。按序匹配，先中先得。
_CAPABILITY_RULES: list[tuple[CapabilityKind, str, re.Pattern[str]]] = [
    # 出/来/做/生成 + 数量词 + 题类："出5道题""来几道练习题""生成10道选择题"
    (
        CapabilityKind.EXERCISE,
        "verb_count_exercise",
        re.compile(
            r"(出|来|做|生成|设计)" + _NO_PAST + (_FILL % 6)
            + r"(\d+|[一两二三四五六七八九十几]+)\s*道" + (_FILL % 8)
            + r"(题|试题|选择题|填空题|判断题|简答题|计算题|练习|习题)"
        ),
    ),
    (
        CapabilityKind.EXERCISE,
        "verb_set_exercise",
        re.compile(
            r"(出|来|做|生成|设计|给我)" + _NO_PAST + (_FILL % 4)
            + r"(一套|一份|几道|些)" + (_FILL % 4) + r"(题|练习|习题|试卷|卷子)"
        ),
    ),
    # 动词 + 学科/题型 + 题类产物，**不要求数量词**：
    # "生成六级填词的题目""出几道英语选择题""帮我生成练习题"
    # 此前只认"数量词 + 道"，导致"生成六级填词的题目"这类正常请求
    # 被判成 NORMAL_CHAT，进而在答疑路径上被"仅回答 AI"的人设拒掉。
    #
    # 负向断言 `_NO_SPECIFIC`：排除"这道题/那道题/该题"这类**特指已有题目**的说法
    # （"帮我做这道题"是要解题，不是要出题），它们应继续回落 NORMAL_CHAT。
    (
        CapabilityKind.EXERCISE,
        "verb_topic_exercise",
        re.compile(
            r"(出|来|做|生成|设计|给我|帮我|请)" + _NO_PAST + (_FILL % 12)
            + r"(?<!这道)(?<!那道)(?<!该)"
            + r"(题|题目|试题|练习题|习题|试卷|卷子|填空|选词填空|选择题|判断题"
            r"|简答题|计算题|阅读理解|完形填空)"
        ),
    ),
    # 画/绘制/生成 + 图类产物："画一张TCP三次握手流程图""帮我做个思维导图"
    (
        CapabilityKind.VISUALIZATION,
        "draw_diagram",
        re.compile(
            r"(画|绘制|生成|做)" + _NO_PAST + (_FILL % 8)
            + r"(一张|一幅|一个|一下|个|出)?" + (_FILL % 10)
            + r"(流程图|架构图|结构图|关系图|对比图|曲线图|示意图|时序图"
            r"|思维导图|脑图|概念图|层次图|图表|流程|架构|曲线|图)"
        ),
    ),
    # 生成/构建/展示 + 知识图谱："帮我生成知识图谱""看看我的知识图谱"
    (
        CapabilityKind.VISUALIZATION,
        "knowledge_graph_request",
        re.compile(
            r"(生成|构建|画|绘制|展示|查看|打开|看看|看)" + _NO_PAST
            + (_FILL % 6) + r"(知识图谱|图谱)"
        ),
    ),
    # 制定/规划/安排 + 计划/路径："基于本周课程制定7天计划""帮我规划复习路径"
    (
        CapabilityKind.PLAN,
        "make_plan",
        re.compile(
            r"(制定|规划|安排|生成|设计|做)" + _NO_PAST + (_FILL % 8)
            + r"(学习计划|计划|学习路径|路径|路线|日程)"
        ),
    ),
    # 祈使/整理动词 + 资料类产物："帮我找几个学习资源""生成10张闪卡"
    (
        CapabilityKind.RESOURCE,
        "request_material",
        re.compile(
            r"(帮我|给我|请|生成|整理|推荐|提供)" + (_FILL % 12)
            + r"(资源|资料|讲义|教程|课件|大纲|文档|学习材料|幻灯片|PPT|ppt"
            r"|闪卡|记忆卡|卡片|笔记)"
        ),
    ),
]


class CapabilityGate:
    """一级能力守门员。decide() 为纯函数，无 IO、无 LLM。"""

    def decide(
        self,
        message: str,
        mode: str = "auto",
        student_profile: dict | None = None,
        context: dict | None = None,
    ) -> CapabilityDecision:
        if mode != "auto":
            kind = _MODE_TO_KIND.get(mode)
            if kind is not None:
                return CapabilityDecision(
                    kind=kind,
                    reason=f"explicit_mode:{mode}",
                    confidence=_EXPLICIT_MODE_CONFIDENCE,
                )
            # 未知显式 mode：守门员不拦（交由下游按既有语义兜底为答疑）
            return CapabilityDecision(
                kind=CapabilityKind.NORMAL_CHAT,
                reason=f"unknown_mode:{mode}",
                confidence=_NORMAL_CONFIDENCE,
            )

        if not message or not message.strip():
            return CapabilityDecision(
                kind=CapabilityKind.NORMAL_CHAT,
                reason="empty_message",
                confidence=_NORMAL_CONFIDENCE,
            )

        matched = self._match_capability(message)
        if matched is None:
            return CapabilityDecision(
                kind=CapabilityKind.NORMAL_CHAT,
                reason="no_capability_evidence",
                confidence=_NORMAL_CONFIDENCE,
            )

        kind, rule = matched
        if _QUESTION_RE.search(message) and not _IMPERATIVE_RE.search(message):
            return CapabilityDecision(
                kind=CapabilityKind.NORMAL_CHAT,
                reason=f"question_over_capability:{rule}",
                confidence=0.6,
            )

        return CapabilityDecision(
            kind=kind,
            reason=f"capability_evidence:{rule}",
            confidence=_CAPABILITY_CONFIDENCE,
        )

    def _match_capability(self, message: str) -> tuple[CapabilityKind, str] | None:
        for kind, rule, pattern in _CAPABILITY_RULES:
            if pattern.search(message):
                return kind, rule
        return None
