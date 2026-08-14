# 资源生成 Workflow Agent 工程化改造规格

## 目标

将“资源生成”收敛为项目的 AI Agent 工程展示主线：在不重写现有产品的前提下，建立一条可解释、可回退、可评测的有界 Workflow。

该项目的简历定位为“AI Agent 工程师”，AI 应用能力作为辅助证明。展示重点是状态边界、编排协议、质量门控、失败处理和验证证据，而不是 Agent 数量或功能数量。

## 事实基线

当前主调用链路：

```text
RouterAgent → ResultAgent → ResourceCenter → ResourceGenWorkflow
→ Director → 单个 Specialist Agent → Finalize
```

`ResourceGenWorkflow` 当前通过 Director 在内容、代码、项目、思维导图、闪卡、交互图解等 Specialist 中选择一个执行。它是模块化 Workflow，但资源链路本身不是严格的多 Agent 协作。

已有能力应被复用：

- `ResourceCenter` 的澄清、用户画像传入和统一结果包装；
- `ResourceGenWorkflow` 的 LangGraph 状态图、SSE 队列、生成失败降级；
- `Director` 的“显式类型 → 规则 → LLM 兜底”路由策略；
- `tests/test_e2e_resource_workshop.py` 的端到端测试骨架；
- 已有资源/图解 Judge Prompt 的领域规则内容。

## 本轮范围

### 要做

1. 让资源生成成为有界角色协作：Planner、Specialist、Validator/Judge、Finalizer。
2. 明确一次运行内的 State 与跨会话画像/记忆的边界。
3. 为 `content` 与 `interactive_diagram` 建立轻量质量门控。
4. 支持一次有限修复、可靠降级与可理解的 SSE 进度。
5. 补足针对上述行为的 mock 测试、SSE 集成测试和少量真实模型冒烟证据。

### 不做

- 不重写 RouterAgent、ResultAgent、Center 总体架构。
- 不把所有六类资源同时纳入 LLM Judge。
- 不新增无限循环、自治 Planner、全局共享记忆或并行 Agent 总线。
- 不修改前端交互协议；前端只消费现有 SSE 事件类型和新增阶段名。
- 不把 LLM Judge 当作事实验证器或百分制精密评分器。

## 目标架构

```text
ResourceCenter
  └─ ResourceGenWorkflow
       ├─ plan: Director / Planner
       ├─ generate: 一个 Specialist Agent
       ├─ validate: 确定性结构校验
       ├─ review: 轻量 LLM-as-Judge（仅两类资源）
       ├─ repair: 原 Specialist，最多一次
       └─ finalize: 确定性聚合与对外响应
```

行为规则：

- Validator 失败时，草稿不能直接交付。
- Judge 只能建议一次修复；它的主观结论不能丢弃已通过 Validator 的可用结果。
- Repair 后再次 Validator；若仍可用但 Judge 仍建议优化，则返回结果并在内部标记 `needs_improvement`。
- Judge 超时或异常时，返回已通过 Validator 的草稿并标记 `skipped`。
- Specialist 与修复均无法形成合法结构时，走现有内容降级；降级仍失败才返回统一错误结果。

## State 与数据边界

`ResourceGenState` 保持为单次运行的显式状态，新增或规范以下字段：

| 分类 | 字段 | 说明 |
| --- | --- | --- |
| 请求 | `run_id`、`topic`、`resource_type`、`student_profile` | 本次输入事实；画像是快照 |
| 计划 | `agent_name`、`sub_type`、`outline`、`route_strategy` | Planner 的可解释决策 |
| 产物 | `draft_blocks`、`content_blocks`、`response` | 草稿与最终交付分离 |
| 质量 | `validation_result`、`review_status`、`review_reason`、`repair_instructions` | 不存储自由文本对话历史 |
| 控制 | `repair_attempted`、`stage_timings`、`error`、`event_queue` | 生命周期与可观测性数据 |

长期用户画像、对话历史和持久化记录继续由现有服务负责。Workflow 只能使用请求开始时传入的画像快照，不能把一次运行的中间状态当作跨会话记忆。

## Agent 协议

### Planner / Director

输入：主题、显式资源类型、画像快照。
输出：目标 Specialist、子类型、可选大纲、路由策略和路由原因。

### Specialist

输入：规划结果与其必要上下文。
输出：标准化 `content_blocks` 与简短 `response`。不直接宣布任务成功。

### Validator

不调用 LLM。检查内容块非空、必填字段、资源类型匹配，以及指定类型的基础格式。

- `content`：至少有可读内容块、标题/正文结构完整。
- `interactive_diagram`：至少有可渲染的内容和对应类型字段；进一步语法校验以现有渲染格式能力为准。

### Judge

仅在 Validator 通过后调用，只输出：

```json
{
  "decision": "pass | repair",
  "reason": "一句话原因",
  "fixes": ["最多三条具体修改建议"]
}
```

Judge 只判断：请求匹配度、最低可用结构、明显跑题/自相矛盾/不可用问题。它不声称证明事实正确，也不返回五维分数。

### Repair 与 Finalizer

Repair 将原计划、草稿和 Judge 建议交回同一个 Specialist，最多一次。Finalizer 不调用 LLM，只负责生成统一响应、最终内容块、运行状态和 SSE 结束事件。

## 失败、回退与 SSE

| 场景 | 后端策略 | SSE 表现 |
| --- | --- | --- |
| 输入不合法 | API 返回 4xx | 不创建流 |
| 路由不确定 | 规则 → LLM → 默认 `content` | `plan` 正常结束 |
| Specialist 失败 | 现有内容生成降级 | `fallback` 进度事件 |
| Validator 失败 | Repair 一次；再失败则降级/错误 | `repair` 或 `fallback` 进度事件 |
| Judge 建议修复 | Repair 一次后再做结构校验 | `review`、`repair` 进度事件 |
| Judge 不可用 | 交付已验证草稿 | `review` 正常结束，内部标记 `skipped` |
| 最终失败 | 统一错误结果 | 先发错误信息，仍保证一个 `done` |

事件类型保持现有 `stage_start`、`stage_end`、`error`、`done`；只扩展阶段名：`review`、`repair`、`fallback`。非致命的 Judge 跳过或质量不足不发前端失败事件。每次请求始终只发送一个最终 `done`。

## 验证策略

继续复用并扩展 `tests/test_e2e_resource_workshop.py`，新增覆盖应分为四层：

1. **Validator 单测**：两类资源的合法与非法内容块。
2. **Workflow mock 测试**：直接通过、触发一次修复、Judge 跳过、修复后失败、内容降级。
3. **SSE 集成测试**：阶段顺序正确、非致命问题不转成前端失败、仅一个 `done`。
4. **真实模型冒烟**：固定 4 个样例（2 个 `content`、2 个 `interactive_diagram`），人工复核生成结果和耗时。

日常 CI/本地全量测试只使用 mock；真实模型冒烟按需手动执行，不作为稳定性断言的唯一依据。

记录但不预设虚假目标值的指标：路由命中、结构化输出有效、修复触发、修复后可交付、端到端耗时、Judge 跳过原因。

## 实现阶段与验收顺序

### Phase 0：保留基线

先运行现有资源工坊 mock 测试，记录当前通过情况和一次代表性 SSE 输出。此阶段不改变行为。

验收：当前资源生成 API、六类已有资源路由和 SSE 测试不回退。

### Phase 1：State 与确定性 Validator

在 `ResourceGenWorkflow` 中明确草稿、最终结果、运行状态与阶段耗时；实现 `content`、`interactive_diagram` 的 Validator。先让 Validator 只记录结果，不触发修复，以保证状态改造可单独验证。

验收：两类资源的合法/非法样例均能给出稳定 Validator 结果；其他四类资源保持原路径。

### Phase 2：轻量 Judge 与一次 Repair

接入简化 Prompt 和结构化解析，将 `pass | repair` 接入 LangGraph 条件边。Repair 复用原 Specialist，最多一次；Judge 异常按 `skipped` 处理。

验收：mock 测试可证明 pass 不修复、repair 只执行一次、Judge 不可用不阻塞。

### Phase 3：失败回退与 SSE 对齐

补齐 Validator 失败、Repair 失败、Specialist 异常的回退分支；在现有事件协议中加入 `review`、`repair`、`fallback` 阶段。

验收：所有分支最终只有一个 `done`；非致命问题不被前端当成失败；真正错误有可理解提示。

### Phase 4：测试与运行证据

扩展 mock 单测和 SSE 集成测试；运行四个固定真实模型样例，记录结果、耗时和已知限制。把验证结论写入项目文档，不伪造指标。

验收：自动化测试通过，真实样例可复现，保留一组可用于演示与面试复盘的证据。

### Phase 5：简历化沉淀

更新 README 的架构描述、补充关键设计决策和面试问答。简历只描述已经实现且验证过的能力。

验收：可以完整讲清 Problem、Constraints、Options、Decision、Trade-off 和 Result；能够区分当前实现与未来规划。

## 文件职责

实现时优先保持现有目录边界：

- `ai-service/app/workflows/resource_gen.py`：状态图、节点编排和条件边。
- `ai-service/app/orchestration/director.py`：保持现有路由职责，不承担质量评估。
- `ai-service/app/agents/`：放置轻量 Reviewer 的 LLM 调用封装；复用既有 Prompt 内容，不复制评分体系。
- `ai-service/app/events/types.py`：复用事件类型，只允许新增阶段语义，不改变前端数据协议。
- `ai-service/tests/test_e2e_resource_workshop.py`：保持端到端契约；新增小而明确的专项测试文件仅用于 Validator/Reviewer 行为。

## 风险与取舍

- LLM Judge 不稳定，因此它仅建议修复，不能作为唯一真相来源。
- 多角色增加延迟，因此只对两类核心资源启用，并限制一次 Repair。
- 只验证基础结构无法证明内容绝对正确，因此真实模型样例必须人工复核，且简历不写未经验证的质量数字。
- 本轮不追求六类资源一致的质量治理；先让一条 Workflow 可解释、可验证，再扩展。

## 完成定义

本轮完成的标志不是“增加了一个 Reviewer”，而是：

1. 两类资源有清楚的结构校验与轻量质量门控。
2. 生成、Judge、修复、回退的状态转换有上限且可追踪。
3. SSE 能准确反映阶段而不误报非致命失败。
4. 自动化 mock 测试和固定真实样例共同证明行为。
5. README、设计决策和简历表述只使用已验证事实。
