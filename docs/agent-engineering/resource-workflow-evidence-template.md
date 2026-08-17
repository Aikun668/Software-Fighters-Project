# 资源 Workflow 质量门控 — 人工复核证据模板

> 用途：对固定 6 案例的真实模型运行结果做人工复核，与 Judge 结论对照，形成前后对比证据。
> 原始 JSONL 运行记录与 diagram 产物存放在 `ai-service/temp_file/evidence/`（已 gitignore，不提交）。
> 本模板只填写人工整理结论，不粘贴原始模型输出全文。

## 运行记录字段

每次运行的最小字段：`case_id`、`run_id`、`workflow_version`、`route_agent`、`route_strategy`、
`stage_timings`、`validation_result`、`review_status`、`repair_attempted`、`fallback_used`、
`final_status`、`error_type`、`elapsed_ms`；diagram 案例额外有 `diagram_source`、`diagram_schema_version`、`diagram_artifact_path`。

## 人工复核表（本轮：real + shadow，schema v1）

| case_id | 人工标记 | Judge 结论 | 是否一致 | diagram_source | schema | 节点/边与主题 | 耗时(ms) | 已知限制 |
|---------|---------|-----------|---------|----------------|--------|--------------|---------|---------|
| content-transformer-basics | 应修复 | repair | 一致 | — | — | — | 157690 | SafetyPipeline 曾记录 violence 日志，尚未证明与 Judge repair 存在因果关系 |
| content-cnn-rnn-comparison | 可交付 | pass | 一致 | — | — | — | 42372 | — |
| content-backprop-intro | 可交付 | pass | 一致 | — | — | — | 126806 | — |
| diagram-cnn-architecture | 可交付 | pass | 一致 | model | v1 | 匹配（输入→卷积→池化→全连接→输出，10 节点 9 边） | 43306 | — |
| diagram-backprop-flow | 可交付 | pass | 一致 | model | v1 | 匹配（前向→损失→反向→梯度→更新，8 节点 8 边） | 40696 | — |
| diagram-attention-flow | 可交付 | pass | 一致 | model | v1 | 匹配（token→QKV→注意力→跨注意力，11 节点 11 边） | 70008 | — |

**diagram 复核结论**：3/3 案例 `diagram_source=model`（非 fallback）、`schema_version=v1`、
节点/边与主题匹配、Judge 均判 pass 且与人工一致；Schema 满足组件渲染约束（节点 2–12、边 1–24、layer 0–5）。
节点点击详情由 `StructuredDiagram` 组件测试（vitest 4/4）证明可渲染交互。

## 三轮运行对比（diagram 案例）

- 基线（off）：改造前为 HTML 产物（解析失败 → fallback 静态 SVG → Judge 判 repair）。
- Shadow（本轮）：Schema v1 产物，只记录 Validator/Judge，不改变产物。

| 指标 | 基线(off，HTML) | Shadow(schema v1) |
|------|----------------|-------------------|
| diagram_source=model | 0/3（HTML 解析失败） | **3/3** |
| 结构化输出有效 | 0/3 | **3/3** |
| Judge 结论 | 3/3 repair | **3/3 pass** |
| 单案例耗时 | 175–205s | **40–70s** |

Active 轮未运行：diagram 证据通过前继续维持 shadow，不切 active。

## 结论（不把样本结果包装成泛化质量结论）

- **哪些问题被修复**：diagram 从「模型生成 HTML → JSON 解析失败 → fallback → Judge repair」变为「模型生成 Schema v1 → 解析成功 → model 产物 → Judge pass」；3/3 案例 source=model、schema=v1、主题匹配。
- **哪些仍需人工判断**：content-transformer-basics 被 Judge 判 repair 的原因待查——SafetyPipeline 曾记录 violence 日志，但尚未证明该日志与 Judge repair 存在因果关系（未改任何安全规则）；content 产物未单独保存 artifact，未做逐字复核。
- **Judge 误判情况**：无（diagram 3/3 pass 与人工一致）。
- **新增延迟**：diagram 单案例 40–70s（含 plan/generate/review），较 HTML 版 175–205s 明显下降。
