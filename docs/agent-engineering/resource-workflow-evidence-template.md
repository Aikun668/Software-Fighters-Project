# 资源 Workflow 质量门控 — 人工复核证据模板

> 用途：对固定 6 案例的真实模型运行结果做人工复核，与 Judge 结论对照，形成前后对比证据。
> 原始 JSONL 运行记录存放在 `ai-service/temp_file/evidence/`（已 gitignore，不提交）。
> 本模板只填写人工整理结论，不粘贴原始模型输出全文。

## 运行记录字段

每次运行的最小字段：`case_id`、`run_id`、`workflow_version`、`route_agent`、`route_strategy`、
`stage_timings`、`validation_result`、`review_status`、`repair_attempted`、`fallback_used`、
`final_status`、`error_type`、`elapsed_ms`。

## 人工复核表

对每个 case，人工标记为「可交付 / 应修复 / 不可交付」，并与 Judge 的 pass/repair 对照。

| case_id | 人工标记 | Judge 结论 | 是否一致 | 修复是否改善 | 耗时(ms) | 已知限制 |
|---------|---------|-----------|---------|-------------|---------|---------|
| content-transformer-basics |  |  |  |  |  |  |
| content-cnn-rnn-comparison |  |  |  |  |  |  |
| content-backprop-intro |  |  |  |  |  |  |
| diagram-cnn-architecture |  |  |  |  |  |  |
| diagram-backprop-flow |  |  |  |  |  |  |
| diagram-attention-flow |  |  |  |  |  |  |

## 三轮运行对比

- 基线（off）：改造前等价行为。
- Shadow：只记录 Validator/Judge 结论，不改变产物。
- Active：允许一次 Repair。

| 指标 | 基线(off) | Shadow | Active |
|------|----------|--------|--------|
| 路由命中 |  |  |  |
| 结构化输出有效 |  |  |  |
| 修复触发 | — |  |  |
| 修复后可交付 | — |  |  |
| Judge 跳过原因 | — |  |  |

## 结论（不把样本结果包装成泛化质量结论）

- 哪些问题被修复：...
- 哪些仍需人工判断：...
- Judge 误判情况：...
- 新增延迟：...
