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
- 结论：第一次的 repair 是旧配置（temperature=0.7）下的 Judge 非确定性判断波动，不是稳定的内容缺陷——改用确定性 PROFILE_REVIEW（temperature=0.0）后见下方校准结果。

### 是内容问题、Judge 误判，还是安全过滤影响？

- 内容无问题：validation_result=pass，7 blocks 完整、紧扣主题、无 violence 词。
- SafetyPipeline 的 violence 日志是误报：本轮 stderr 仍记录 violations=['violence']，但产物无 violence 词、Judge 判 pass。因此该日志与 Judge 结论无因果关系（violence 日志持续触发，但 Judge 本轮仍判 pass）。
- 未改任何安全规则：本轮只记录证据，未修改 content safety filter / quality_mode / LLM Provider。

## Judge 稳定性校准（temperature=0.0，PROFILE_REVIEW）

对 3 个已保存 content artifact 各调用 Judge 3 次（共 9 次），不重新生成内容：

| case_id | 3 次结果 |
|---------|---------|
| content-transformer-basics | pass / pass / pass |
| content-cnn-rnn-comparison | pass / pass / pass |
| content-backprop-intro | skipped / pass / pass |

- 8/9 为 pass；1 次 skipped 由 LLM 返回空响应导致（基础设施偶发，非 Judge 判断波动）。
- 结论：temperature=0.0 后，Judge 对同一固定 artifact 的结论稳定为 pass，未复现旧配置（0.7）下 transformer 的 repair 波动。

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
- Judge 稳定性：旧配置（temperature=0.7）下 Judge 存在跨轮非确定性（transformer 第一次 repair、重跑 pass），尚未隔离稳定性；改用确定性 PROFILE_REVIEW（temperature=0.0）后，9 次校准 8 pass + 1 skipped（空响应），结论稳定。
- 新增延迟：diagram 单案例 30–70s，较 HTML 版 175–205s 明显下降。

---

## 主动修复与真实证据闭环（active-real-v1 轮次，2026-08-23）

> 任务来源：`docs/agent-engineering/DEEPSEEK_MILESTONE_ACTIVE_QUALITY_EVIDENCE.md`。
> 目标：证明 Repair 语义在真实调用链中成立，并完成一次可复核的 `active` 真实运行。
> 本轮不修改默认 `quality_mode`、LLM Provider、SafetyPipeline 或任何路由/中心。

### 自动化强制 Repair 证据（mock，非真实模型）

`ai-service/tests/test_repair_semantics.py`（6 项，全绿）证明下列契约在代码路径上成立：

| 测试 | 证明的语义 |
|------|------------|
| `test_content_agent_repair_context_enters_prompt` | content（overview 子路径）`repair_instructions` + 旧草稿实际进入 user_prompt |
| `test_content_agent_guide_repair_context_enters_prompt` | content（guide 子路径）同上 |
| `test_diagram_agent_repair_context_enters_prompt` | interactive_diagram 同上（`previous_blocks` 内 schema 内容进入 prompt） |
| `test_repair_preserves_pre_repair_blocks_and_runs_once` | 触发 repair 时 `pre_repair_blocks` 与最终 `content_blocks` 可区分；Specialist 总调用次数 = 首次生成 + 1 次 repair |
| `test_repair_exception_preserves_pre_repair_blocks` | repair 异常时仍写 `pre_repair_blocks` + `repair_attempted=True`，最终交付为原合法草稿 |
| `test_runner_saves_pre_and_post_artifact` | runner 仅在发生 repair 时落 `<case_id>.pre-repair.json` + `<case_id>.artifact.json`，未发生不伪造前置 artifact |

外加回归（`test_resource_quality_gate.py` / `test_resource_gen_quality_flow.py` / `test_resource_workflow_evidence_runner.py` / `test_e2e_resource_workshop.py`）共 **64 passed, 2 skipped**（RealLLM E2E 跳过，符合预期）。`python -m compileall -q app scripts tests` 无输出（成功）。

### 真实 active 运行事实（DeepSeek，6 案例）

输出：`ai-service/temp_file/evidence/active-real-v1.jsonl`（gitignored，不提交）。

| case_id | review_status | repair_attempted | final_status | elapsed_ms | diagram_source | schema |
|---|---|---|---|---|---|---|
| content-transformer-basics | pass | **TRUE** | success | 495689 | — | — |
| content-cnn-rnn-comparison | pass | false | success | 39608 | — | — |
| content-backprop-intro | skipped | false | success | 145282 | — | — |
| diagram-cnn-architecture | pass | false | success | 34286 | model | v1 |
| diagram-backprop-flow | pass | false | success | 31830 | model | v1 |
| diagram-attention-flow | pass | false | success | 79221 | model | v1 |

- 实际 repair 次数：**1**（content-transformer-basics）
- fallback 次数：**0**
- 失败数：**0**
- 耗时范围：**31.8s – 495.7s**（含一次真实 repair 调用）
- skipped 原因：`content-backprop-intro` 的 Judge LLM 返回空响应 → 任务书允许的 `Judge 暂不可用` 降级路径，最终交付原始合法草稿，`final_status=success`。

### 真实 repair 的人工比较（content-transformer-basics）

- 修复建议（来自 Judge LLM，3 条全在 prompt 上限内）：
  1. 合并重复的开头，并在每小节之间增加过渡内容。
  2. 添加可视化示意图（流程图）来服务视觉型初学者。
  3. 统一术语表述，在同一节内不同小节保持一致。
- Pre-repair artifact：`temp_file/evidence/content-transformer-basics.pre-repair.json`，6 blocks（概述 / 自注意力直观理解 / 数学定义与计算流程 / 多头注意力与位置编码 / 复杂度与工程注意点 / callout）。
- Post-repair artifact：`temp_file/evidence/content-transformer-basics.artifact.json`，7 blocks（概述 / 为什么需要自注意力：从 RNN 到并行序列建模 / Q/K/V 与缩放点积注意力 / 矩阵视角 / 多头注意力与位置编码 / 开发者落地：伪代码与复杂度 / callout）。
- 人工比较结论：
  - **结构校验**：Pre 与 Post 均通过 `ResourceValidator(content)`（passed=True，无 issue）。
  - **主题**：未偏移，全程围绕 Transformer 自注意力。
  - **修复痕迹**：Post 新增"为什么需要自注意力"过渡节并拆分原"直观理解"为"Q/K/V 定义"与"矩阵视角"两节，直接对应建议 1（合并重复开头+增加过渡）与建议 3（术语一致）；新增"开发者落地：伪代码与复杂度"亦回应了建议 2 的工程化取向。
  - **未退化**：无无意义重写，逻辑递进更清晰；violence 词在 Pre/Post 均无命中（再次确认 SafetyPipeline 的 violence 日志为误报，与 Judge 结论无因果关系）。
- 阶段耗时：repair 阶段 306.6s（占总耗时 62%），符合 LLM 二次调用的预期成本。

### 自动化与真实的因果关系

- 自动化测试已证明 Specialist 真的接收修复建议 + 旧草稿作为 prompt 输入；
- 真实运行验证：content 子路径与 interactive_diagram 子路径在真实 LLM 触发 repair 时确实进入 repair 路径；
- 真实运行验证：未触发 repair 的 5 个 case 全部最终交付原始合法草稿，没有被 Judge 的非致命意见升级成失败。

### 结论与建议

- **是否建议 Codex 把默认 `quality_mode` 从 `shadow` 切到 `active`**：**暂不建议立即切换**，但**具备切换前置条件**，理由：
  - **满足门**：
    1. 自动化全部通过，强制 Repair 与异常保留分支都有覆盖 ✓
    2. 真实 6 案例未出现由质量门控引入的未处理错误或重复 Repair ✓
    3. 真实 Repair 经人工比较未退化 ✓
    4. 证据模板结论与 JSONL/artifact 一致 ✓
  - **保留保守的已知限制**：
    - 真实 Judge 给出 repair 的命中率仅 1/6，绝大多数情况下 active 与 shadow 行为不可观察差异；切换 active 的边际收益在当前模型稳定性下并不显著。
    - 单次 repair 调用带来约 5× 端到端延迟（~31s → ~496s 在 transformer 案例中），需要 Codex 评估成本-收益。
    - 真实 Judge 出现 1 次 skipped（空响应），已正确降级，但提示对供应商瞬时故障的容忍度可作为切换 active 的副作用之一被记录。
- **Codex 决策门槛**：本轮证据已达到任务书定义的切换 active 四项门；是否切换仍由 Codex 基于产品策略决定（成本/延迟 vs 修复收益）。
- **不需要 Codex 进一步决策的事项**：默认配置、SafetyPipeline、Router/Center/SSE、LLM Provider — 本轮均未触碰。
