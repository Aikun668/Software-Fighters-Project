"""意图决策的输出对象：只表达"用户想做什么"，不含执行者、顺序与依赖。

纯数据、无业务 import。`RouterAgent.decide` 产出它，`PlanBuilder.build` 消费它。

【决策所有权】意图判定结论的载体 —— 由 `RouterAgent.decide` 独产，`PlanBuilder` 只读。
"""

from dataclasses import dataclass, field
from typing import Any, Literal

DecisionSource = Literal["empty", "manual", "keyword", "fallback"]


@dataclass(frozen=True)
class RouteCandidate:
    intent: str
    # 人工规则的确定性打分，不是概率；当前没有校准器，不得当作置信度解读
    rule_score: float
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RouteDecision:
    source: DecisionSource
    message: str
    candidates: tuple[RouteCandidate, ...] = ()
    # 用户显式点选的功能入口（source == "manual" 时有值）
    manual_mode: str | None = None
    is_clear: bool = True
    inquiry: str | None = None
