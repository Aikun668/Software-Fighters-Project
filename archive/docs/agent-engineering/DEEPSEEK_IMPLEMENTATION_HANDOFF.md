# DeepSeek Harness 实施交接单

## 你的角色

你是本项目的实施工程师。负责在现有架构内完成代码、测试和小粒度提交；不要自行改变产品方向或重新设计 Agent 架构。

Codex 负责架构决策、任务拆分、验收标准、问题分析和后续优化。遇到范围、架构或产品取舍，请停下并把事实与选项反馈给 Codex。

## 先阅读

1. `AGENTS.md`
2. `docs/agent-engineering/PRINCIPLES.md`
3. `docs/superpowers/specs/2026-08-14-resource-workflow-agent-engineering-design.md`
4. `docs/superpowers/plans/2026-08-14-resource-workflow-quality-gate.md`

实施以最后一份计划为唯一任务顺序；不要顺手重构 Router、ResultAgent、ResourceCenter、前端或 SSE 协议。

## 当前目标

将现有单 Specialist 资源生成链路升级为受限质量工作流：

`Planner / Director → Specialist → Validator → Judge → Repair（最多一次）→ Finalizer`

第一版 Judge 只覆盖 `content` 和 `interactive_diagram`。其他资源类型维持原路径。

## 实施规则

- 严格按计划的 Task 1 至 Task 5 顺序执行；每个 Task 先补/写失败测试，再实现最小代码，再运行该 Task 指定的测试。
- 保持外层调用链不变：`RouterAgent → ResultAgent → ResourceCenter → ResourceGenWorkflow`。
- 将质量逻辑集中在 `app/services/resource_quality_gate.py` 与 `app/workflows/resource_gen.py`；Prompt 仍放在现有 YAML 目录。
- 支持三种模式：`off`（行为等价基线）、`shadow`（记录但不干预）、`active`（允许一次 Repair）。
- Validator 是硬约束；Judge 只输出 `pass | repair | skipped`，不做五维评分，不承担事实校验。Judge 异常必须降为 `skipped`，不能阻断交付。
- 任意路径最多一次 Repair、最多一个最终 `done` SSE 事件。非致命 Judge 状态不发送 `error` SSE。
- 不新增依赖；不提交真实模型 JSONL、日志或密钥。

## 每个任务完成后反馈给 Codex

按下面格式简短汇报：

```text
Task N 完成情况：完成 / 阻塞
改动文件：...
实现摘要：...
验证命令与结果：...
提交：<hash> <message>（如已提交）
风险或需要决策：无 / ...
```

如果测试失败，不要用删除测试、放宽断言或吞异常来“通过”。先报告失败现象、最小复现、可能原因和建议方案，等待 Codex 决策。

## 首个执行指令

从计划的 **Task 1：建立质量门控契约与确定性 Validator** 开始。先检查现有输出 block 格式与测试约定；仅在它们与计划冲突时，带着具体证据向 Codex 提问。
