"""二级意图决策（关键词 → `RouteDecision`）—— **不是** LLM Agent。

【决策所有权】二级请求级意图判定 —— 本模块是唯一拥有者。
  - 唯一调用点：`ChatCenter.route`（`app/centers/chat_center.py`）
  - 输入：用户消息 + mode；输出：`RouteDecision`（候选意图 + 规则分），
    不选执行者、不排顺序、不建 `ExecutionPlan`（属 `PlanBuilder`）
  - 关键词表来源：`app.services.intent_extractor.INTENT_REGISTRY`
    （本模块只做打分与取舍，**不另建关键词表**）
  - ⚠️ `_QMARKS`（本模块内）与 `INTENT_REGISTRY["tutor_question"].keywords` 语义相近、
    **有意独立维护**：两者关键词集合不同，合并会改变路由行为（P3 决定：只登记，不合并）
  - 禁止：决定「是否进入专项能力」（一级属 `CapabilityGate`）；
    禁止选择资源 Agent（属 `Director`）
  - 约定：`temp_file/9.15工程改造计划/0、产品方向与约束/三类决策与命名约定.md`

【命名澄清】名字叫 `RouterAgent`，但它 **不是 Center**（却位于 `app/centers/`）、
  **不是 LLM Agent**（`decide()` 全程无 LLM 调用），实为「关键词 → RouteDecision」
  的纯规则判定器。改名排在 P3-B，本轮只标注。
"""

import logging

from app.centers.plan_builder import PlanBuilder
from app.centers.route_decision import RouteCandidate, RouteDecision
from app.centers.schemas import ExecutionPlan
from app.services.capability_map import INTENT_CENTER_MAP, MODE_TO_INTENT
from app.services.intent_extractor import (
    _INTENT_PRIORITY,
    _MUTEX_GROUPS,
    INTENT_REGISTRY,
    IntentExtractor,
    _mock_extract_params,
    _score_intent,
)

logger = logging.getLogger(__name__)

# 低门槛：关键词命中即可进入评分
_KEYWORD_FLOOR = 0.3
# 高门槛：规则分达标才保留为独立意图
_CONFIDENCE_THRESHOLD = 0.4

_EMPTY_INQUIRY = "你想了解什么？"


class RouterAgent:
    MODE_TO_INTENT: dict[str, str] = MODE_TO_INTENT

    def __init__(self, intent_extractor: IntentExtractor | None = None):
        # `intent_extractor` 参数**保留**以兼容既有测试签名（10 个测试文件构造时传参）；
        # 当前实现只做关键词判定（`_keyword_candidates`），不读取该实例 —— 属 P3-B 登记项，
        # 删除参数会破坏测试契约，故仅保留显式的"未使用"说明。
        del intent_extractor

    def decide(self, message: str, mode: str = "auto") -> RouteDecision:
        if not message.strip():
            # 空输入给追问，不编造意图
            return RouteDecision(
                source="empty",
                message=message,
                is_clear=False,
                inquiry=_EMPTY_INQUIRY,
            )

        if mode != "auto":
            intent = self.MODE_TO_INTENT.get(mode, "tutor_question")
            return RouteDecision(
                source="manual",
                message=message,
                manual_mode=mode,
                candidates=(
                    RouteCandidate(
                        intent=intent,
                        rule_score=1.0,
                        params={"question": message, "topic": message},
                    ),
                ),
            )

        candidates = self._keyword_candidates(message)
        if candidates:
            return RouteDecision(
                source="keyword", message=message, candidates=tuple(candidates)
            )

        return RouteDecision(
            source="fallback",
            message=message,
            candidates=(
                RouteCandidate(
                    intent="tutor_question",
                    rule_score=0.0,
                    params={"question": message.strip()},
                ),
            ),
        )

    async def route(
        self,
        message: str,
        mode: str = "auto",
        student_profile: dict | None = None,
        context: dict | None = None,
        max_intents: int = 5,
    ) -> ExecutionPlan:
        """旧入口：decide + PlanBuilder 的组合，仅为既有测试兼容保留。

        生产路径（`ChatCenter.route`）直接分别调用 `decide` 与 `PlanBuilder.build`。
        """
        return PlanBuilder().build(
            self.decide(message, mode),
            student_profile=student_profile,
            context=context,
            max_intents=max_intents,
        )

    def _keyword_candidates(self, message: str) -> list[RouteCandidate] | None:
        scored = []
        for intent_def in INTENT_REGISTRY:
            score = _score_intent(message, intent_def)
            if score >= _KEYWORD_FLOOR:
                scored.append((score, intent_def))

        if not scored:
            return None

        scored.sort(key=lambda x: -x[0])

        # ── 问题检测 checkpoint：当存在非 auto 意图且输入含疑问标记时，
        #     强制注入 tutor_question，防止"画图+出题"等强工具词吸走答疑意图。
        #     非 auto = 映射到具体中心（visualization/resource/exercise/plan），
        #     排除 tutor_question / solve_problem / diagnose / profile_building / unknown。
        #     _QMARKS 与 tutor_question.keywords 语义相近但独立维护：
        #     此处关注"是否为提问句式"，keyword 评分关注"是否匹配答疑意图"。
        _QMARKS = ["什么", "为什么", "怎么", "如何", "是什么", "?", "？",
                   "解释", "讲讲", "讲解", "说说", "介绍一下", "区别", "分析"]
        _non_auto = [d for _, d in scored
                     if INTENT_CENTER_MAP.get(d.intent, "auto") != "auto"]
        if _non_auto and any(m in message for m in _QMARKS):
            _has_tutor = any(
                d.intent == "tutor_question" and s >= _CONFIDENCE_THRESHOLD
                for s, d in scored
            )
            if not _has_tutor:
                tutor_def = next((d for d in INTENT_REGISTRY
                                  if d.intent == "tutor_question"), None)
                if tutor_def:
                    scored.insert(0, (0.55, tutor_def))
        filtered = list(scored)
        for group in _MUTEX_GROUPS:
            matched = [(s, d) for s, d in filtered if d.intent in group]
            if len(matched) > 1:
                # 同分时按 _INTENT_PRIORITY 打破平局（visualize > resource_gen）
                best_intent = max(matched, key=lambda x: (
                    x[0], _INTENT_PRIORITY.get(x[1].intent, 0)
                ))[1].intent
                filtered = [(s, d) for s, d in filtered
                            if d.intent not in group or d.intent == best_intent]

        # 规则分阈值过滤（替代硬截断），至少保留 1 个
        qualified = [(s, d) for s, d in filtered if s >= _CONFIDENCE_THRESHOLD]
        if not qualified:
            qualified = [max(filtered, key=lambda x: x[0])]

        return [
            RouteCandidate(
                intent=intent_def.intent,
                rule_score=score,
                params=_mock_extract_params(intent_def.intent, message),
            )
            for score, intent_def in qualified
        ]
