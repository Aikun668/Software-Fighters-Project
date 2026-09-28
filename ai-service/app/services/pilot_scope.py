"""试点课程范围（总纲 §5.5 第 1 条；P2 Task 5）。

## 职责边界（先斩后奏，见 tests/test_p2_task5_pilot_whitelist.py 的裁决栏）

- **配置真源在 Java**：谁能试点、试点哪些课，属部署配置（P2 §〇 问题 2 表末行
  `| 试点开关 | ... | Java（配置） |`）。
- **执行闸门在 Python**：读模型对白名单外课程降级为旧行为（P2 §六 Task 表行 5）。

两者不冲突，各说一半 —— Python 零状态、不读 DB（边界规则 1），无法自己决定谁能
试点，只能对传进来的 `course_id` 做判定。本模块就是那个**纯判定**，不含任何 IO。

## 闸门语义（V1 冻结）

- 白名单 = `{"ai_intro"}`（总纲 §5.5 第 1 条；P2 §2.5）；
- **精确匹配、区分大小写**：不做大小写/空白归一化 —— 归一化会**放大**试点范围，
  与「限制试点，不能一上线影响所有课程」的目的相反；
- 判定必须**全域**（对任意输入返回 `bool`）：路由层是系统边界，不得靠调用方先验类型。
"""

from typing import Final

# V1 试点课程白名单（P2 §2.5）。新增试点课程需同时改 Java 配置与这里 —— 两层
# 各自独立，Python 侧不接受运行时注入，避免配置意外放宽试点面。
PILOT_COURSE_IDS: Final = frozenset({"ai_intro"})


def is_pilot_course(course_id: object) -> bool:
    """`course_id` 是否在试点白名单内（精确、区分大小写、总函数）。"""
    return isinstance(course_id, str) and course_id in PILOT_COURSE_IDS
