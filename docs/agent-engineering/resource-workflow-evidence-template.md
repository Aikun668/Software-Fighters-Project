# 资源 Workflow 质量门控 — 人工复核证据模板

> 用途：对固定 6 案例的真实模型运行结果做人工复核，与 Judge 结论对照，形成前后对比证据。
> 原始 JSONL 运行记录与交付 artifact 存放在 ai-service/temp_file/evidence/（已 gitignore，不提交）。
> 本模板只填写人工整理结论，不粘贴原始模型输出全文。

## 运行记录字段

每次运行的最小字段：case_id、run_id、workflow_version、route_agent、route_strategy、
stage_timings、validation_result、review_status、review_reason、repair_attempted、fallback_used、
final_status、error_type、elapsed_ms、artifact_path；
diagram 案例额外有 diagram_source、diagram_schema_version、diagram_artifact_path。

## 人工复核表（最新一轮：real + shadow，schema v1）

| case_id | 人工标记 | Judge 结论 | 是否一致 | diagram_source | schema | 交付产物 | 耗时(ms) |
|---------|---------|-----------|---------|----------------|--------|---------|---------|
| content-transformer-basics | 可交付 | pass | 一致 | — | — | 7 blocks 紧扣主题 | 179364 |
| content-cnn-rnn-comparison | 可交付 | pass | 一致 | — | — | 对比清晰 | 37635 |
| content-backprop-intro | 可交付 | pass | 一致 | — | — | 紧扣主题 | 128255 |
| diagram-cnn-architecture | 可交付 | pass | 一致 | model | v1 | 10 节点 9 边 | 43389 |
| diagram-backprop-flow | 可交付 | pass | 一致 | model | v1 | 8 节点 8 边 | 34338 |
| diagram-attention-flow | 可交付 | pass | 一致 | model | v1 | 11 节点 11 边 | 30581 |

## content artifact 复核（3 个 content 案例）

### Transformer 为什么第一次被判 repair？

- 第一次运行该案例 review_status=repair；本轮重跑同一案例，review_status=pass，review_reason 为「内容紧扣自注意力主题，知识结构合理，分节讲解…可交付」。
- 人工复核本轮 artifact：7 个 content block（6 个 section + 1 个 callout），内容紧扣「Transformer 自注意力」，全文不含 violence 相关词（杀/暴力/武器/爆炸/伤害/攻击 均无命中）。
- 结论：第一次的 repair 是 LLM Judge 的非确定性判断波动，不是稳定的内容缺陷——同一案例重跑即翻转成 pass。

### 是内容问题、Judge 误判，还是安全过滤影响？

- 内容无问题：validation_result=pass，7 blocks 完整、紧扣主题、无 violence 词。
- SafetyPipeline 的 violence 日志是误报：本轮 stderr 仍记录 violations=['violence']，但产物无 violence 词、Judge 判 pass。因此该日志与 Judge 结论无因果关系（violence 日志持续触发，但 Judge 本轮仍判 pass）。
- 未改任何安全规则：本轮只记录证据，未修改 content safety filter / quality_mode / LLM Provider。

## diagram 复核结论（3 个 diagram 案例）

3/3 案例 diagram_source=model（非 fallback）、schema_version=v1、节点/边与主题匹配、
Judge 均判 pass 且与人工一致；Schema 满足组件渲染约束（节点 2–12、边 1–24、layer 0–5）。
节点点击详情由 StructuredDiagram 组件测试（vitest 4/4）证明可渲染交互。

## 三轮运行对比（diagram 案例）

- 基线（off）：改造前为 HTML 产物（解析失败 → fallback 静态 SVG → Judge 判 repair）。
- Shadow（本轮）：Schema v1 产物，只记录 Validator/Judge，不改变产物。

| 指标 | 基线(off，HTML) | Shadow(schema v1) |
|------|----------------|-------------------|
| diagram_source=model | 0/3（HTML 解析失败） | 3/3 |
| 结构化输出有效 | 0/3 | 3/3 |
| Judge 结论 | 3/3 repair | 3/3 pass |
| 单案例耗时 | 175–205s | 30–70s |

Active 轮未运行：diagram 证据通过前继续维持 shadow，不切 active。

## 结论（不把样本结果包装成泛化质量结论）

- 哪些问题被修复：diagram 从「模型生成 HTML → JSON 解析失败 → fallback → Judge repair」变为「模型生成 Schema v1 → 解析成功 → model 产物 → Judge pass」；3/3 案例 source=model、schema=v1、主题匹配。
- content transformer repair 的定性：第一次 repair 未复现——重跑同案例为 pass，且产物无 violence 词；SafetyPipeline 的 violence 日志为误报且与 Judge 结论无因果关系（violence 仍触发但 Judge 判 pass）。未改任何安全规则。
- Judge 误判情况：diagram 3/3 pass 与人工一致；content 的 repair→pass 说明 Judge 存在跨轮非确定性（同一输入不同结论），属 LLM-as-Judge 固有波动，非稳定误判。
- 新增延迟：diagram 单案例 30–70s，较 HTML 版 175–205s 明显下降。
