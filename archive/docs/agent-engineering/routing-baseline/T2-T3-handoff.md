# T2 + T3 · 意图决策拆分与执行边界 · 阶段报告

> 基线：HEAD `882f458`。T1 与 T2/T3 的改动均未提交，留在工作区。
> 性质：结构改造。旧路由行为与 SSE 契约保持不变；未改关键词、映射值、追问/确认的触发时机。

## 一、做了什么

### T2：意图决策与计划构建分离

- `app/centers/route_decision.py`（新）：`RouteDecision` / `RouteCandidate`。只表达候选意图、规则分、来源，不含中心与执行顺序。`rule_score` 明确为规则分，不是概率。
- `app/centers/router_agent.py`：拆为 `decide()`（产出 `RouteDecision`）与 `_keyword_candidates()`（原关键词评分逻辑，未改）。`route()` 保留为兼容壳（`decide` + `PlanBuilder.build`），仅供既有测试使用，生产路径不经过。
- `app/centers/plan_builder.py`（新）：`build(decision)` 生成 `ExecutionPlan`；`build_normal_chat`、`annotate_route` 供 `ChatCenter` 使用。不 import 任何意图侧模块。
- `app/centers/execution_gate.py`（新）：`judge(plan)` 给出 PASS / INQUIRY / CONFIRM 的唯一结论；`blocks_execution` 只对 INQUIRY 返回真。
- `app/centers/chat_center.py`：`route()` 改为 `router.decide` → `PlanBuilder`。gate 权威兜底逻辑不变。`route()` 仍为 async。
- `app/centers/chat_task_dispatcher.py`：inquiry 判断改读 `judge` / `blocks_execution`，不再自行解读 plan 标记。

### T3：执行边界

- Dispatcher 只接收计划、调度任务、收集结果，不重判全局意图。执行层 6 个文件不得 import 意图侧模块，由 AST 测试锁定。
- 未搬动、未删除任何 Center 或 Agent 文件。

## 二、验收结果

| 检查 | 结果 |
|---|---|
| 路由快照（140 条，`probe_routing_snapshot.py`） | 指纹 `2624a51be09b9d5e`，0 异常，0 非确定，与 T0 一致 |
| 路由快照文件 sha256 | `1d4e6830…`，与 T0 一致 |
| SSE 契约（`probe_sse_contract.py`） | sha256 `866a6c6d…`，与 T0 一致 |
| 路由 / Dispatcher / 契约相关 pytest（14 个文件，含 `test_route_plan_split_contract.py`） | 262 passed |
| `test_routing_ownership_contract.py` | 35 passed |

注：T0 探针会覆写基线文件。本轮先把两份基线备份到仓库外并核对一致，再重跑；重跑后输出与备份逐字节相同。

## 三、Gate 核对

**T2-Gate**

- 意图判断不派发、不建最终计划：通过。`router_agent.py` 不构造 `CenterTask` / `ExecutionPlan`，由 AST 测试锁定。
- 计划构建不重新猜意图：通过。`plan_builder.py` 无意图侧 import。
- 单任务与多任务计划稳定可验证：通过（`test_route_plan_split_contract.py`）。
- 追问、确认有明确消费方，行为变化项已隔离：**部分通过**。追问由 Dispatcher 执行；确认由 Dispatcher 消费，但当前只记日志并照常执行（见四·1）。
- T0 快照与 SSE 兼容，现存错误留给 T4：通过。

**T3-Gate**

- 任一任务可定位调度者、产物负责人、失败处理者：通过。调度是 `ChatTaskDispatcher`，产物由各 Center 负责，失败由 `_execute_task` 捕获并转为 error 事件。
- 执行层不覆盖上游意图；域内 Agent 选择与全局路由边界明确：通过（AST 测试）。
- 主要输出与 SSE 契约兼容：通过（SSE sha256 一致）。"关键工作流可独立执行"没有专项验证，依赖既有测试覆盖。
- 不因拆层增加不必要调用环节：通过。本轮未新增 Center / Agent 调用。

## 四、未闭环与需要你决定

1. **CONFIRM 未强制执行。** 带 `needs_confirmation` 的计划（3 个及以上任务）仍照常执行，与旧行为一致。前端没有确认回路，改为阻断属于用户可见的行为变更，需要你单独批准。建议放入 T4-A 讨论。
2. `flashcard_gen`、`code_example`、`adjust_plan` 的闭环仍在 T4-C，本轮未动。
3. `RouterAgent.__init__(intent_extractor=...)` 参数保留但不使用，因为 10 个测试文件依赖该签名。
4. `RouterAgent.route()` 兼容壳保留，仅供测试使用。

## 五、跨 Center / Agent 直接调用清单（T3 步骤 5）

| 调用 | 结论 | 说明 |
|---|---|---|
| `ChatTaskDispatcher` → 5 个 Center | 保留 | 调度的正常路径 |
| `ChatCenter` → 全部 Agent | 保留 | 组装根（`_get_dispatcher` 内构造依赖），未改 |
| `VisualizationCenter` → `TutorAgent` | 保留，待评估 | 可视化复用 TutorAgent 讲解文本，跨域但有真实产物依赖 |
| `AutoCenter` → `VisualizePipeline` | 待评估 | `VisualizationCenter` 也引用同一 pipeline，存在重复入口，后续可考虑收口 |
| `ResourceCenter` → `ResourceGenWorkflow` | 保留 | 资源域自有工作流 |
| `tutor_center.py` / `graph_center.py` | 保留 | 不经 `ChatCenter`，但被 `internal_api/tutor.py`、`graph.py` 引用，属独立入口 |

本轮未搬动、未删除上述任何文件。

## 六、状态

- 已按阶段单位提交（未推送）：T0 基线、T1、T2、T3 各一个提交。
- `chat_center.py` 与 `chat_task_dispatcher.py` 同时包含 T1 与 T2/T3 的改动，已按 hunk 拆分：
  T1 提交写入这两个文件的 T1 中间态（由 `T1.diff` 精确重建，提交时逐文件哈希与 `T1.diff`
  的 post-image 一致），T2 提交再叠加 T2/T3 改动。
- **CONFIRM 裁决（已定）**：本轮维持"不阻断"，即带 `needs_confirmation` 的计划照常执行、
  仅记日志。理由：① 属用户可见行为变更，本轮定位是结构改造；② 140 条基线中
  `needs_confirmation=true` 为 **0 条**，无护栏可判回归；③ 前端尚无确认回路，单侧阻断会
  让对话停在无法继续的状态。**归入 T4-B**（该阶段验收含"用户确认情形下继续/阻断/询问"），
  实施前置条件：先补确认链路的专用用例与前端确认卡。
- T4 及之后未启动。
