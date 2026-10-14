"""执行前裁决：对一份 `ExecutionPlan` 给出 追问 / 确认 / 放行 的唯一结论。

【决策所有权】追问、确认、放行的唯一裁决点；`ChatTaskDispatcher` 只读本结论，
  不再自行解读 plan 的标记位。
  - 追问：阻断执行，由 Dispatcher 下发 inquiry 事件（与旧行为一致）
  - 确认：计划带 `needs_confirmation` 时给出结论，但**当前不阻断**（旧行为即照常执行，
    且没有任何前端确认回路）；改为阻断属于用户可见的行为变更，须另行批准
  - 放行：交 Dispatcher 正常执行
"""

from enum import Enum

from app.centers.schemas import ExecutionPlan


class ExecutionVerdict(str, Enum):
    PASS = "pass"
    INQUIRY = "inquiry"
    CONFIRM = "confirm"


def judge(plan: ExecutionPlan) -> ExecutionVerdict:
    if plan.tasks and plan.tasks[0].mode == "inquiry":
        return ExecutionVerdict.INQUIRY
    if plan.needs_confirmation:
        return ExecutionVerdict.CONFIRM
    return ExecutionVerdict.PASS


def blocks_execution(verdict: ExecutionVerdict) -> bool:
    return verdict is ExecutionVerdict.INQUIRY
