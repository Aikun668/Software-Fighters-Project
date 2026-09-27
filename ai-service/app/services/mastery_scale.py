"""掌握度统一口径（P1 §3.4 冻结，P2 Task 1 落地）。

五级 level 是 P1 冻结的唯一掌握度语义，供读模型 / 建议生成 / 图谱共用。
图谱自有的 3 值 status（locked/learning/mastered）是**展示投影**，不是本模块。

| 掌握度区间 | level |
| --- | --- |
| `null` / `<= 0.0` | `not_started` |
| `(0, 0.3)` | `beginner` |
| `[0.3, 0.6)` | `learning` |
| `[0.6, 0.85)` | `proficient` |
| `[0.85, 1.0]` | `mastered` |
"""

from typing import Final

LEVEL_NOT_STARTED: Final = "not_started"
LEVEL_BEGINNER: Final = "beginner"
LEVEL_LEARNING: Final = "learning"
LEVEL_PROFICIENT: Final = "proficient"
LEVEL_MASTERED: Final = "mastered"

MASTERY_LEVELS: Final = (
    LEVEL_NOT_STARTED,
    LEVEL_BEGINNER,
    LEVEL_LEARNING,
    LEVEL_PROFICIENT,
    LEVEL_MASTERED,
)

# 冻结边界（P1 §3.4）：本模块是这三条阈值的唯一来源。
BEGINNER_LOWER: Final = 0.0
LEARNING_LOWER: Final = 0.3
PROFICIENT_LOWER: Final = 0.6
MASTERED_LOWER: Final = 0.85


def mastery_to_level(mastery: float | None) -> str:
    """掌握度数值 → 五级 level。

    `None`（无记录）与 `0.0` 在 level 上合并为 `not_started`；
    若需区分二者，请在 `mastery.value` 字段保留 `null` / `0.0`（P1 §3.4 注）。
    """
    if mastery is None or mastery <= BEGINNER_LOWER:
        return LEVEL_NOT_STARTED
    if mastery < LEARNING_LOWER:
        return LEVEL_BEGINNER
    if mastery < PROFICIENT_LOWER:
        return LEVEL_LEARNING
    if mastery < MASTERED_LOWER:
        return LEVEL_PROFICIENT
    return LEVEL_MASTERED
