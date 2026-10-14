# T0 · 重构前基线 · 交付说明（Handoff）

> 采集人：Coding Agent A ｜ 采集日期：2026-10-13
> 全程**只读**：未提交 / 未暂存 / 未还原 / 未覆盖任何生产代码；仅新增 `docs/agent-engineering/routing-baseline/` 下的探针与产物。
> 一句话结论：**T0 四个子任务全部完成；路由生产代码零改动；全部产物可复现。**

---

## 一、T0 是否全部完成

| 子任务 | 状态 | 产物 |
|---|---|---|
| T0.1 Git / 工作区保护 | ✅ 完成 | `baseline_workspace_record.md` + `routing_related_uncommitted.diff` |
| T0.2 冻结旧映射表 | ✅ 完成 | `legacy_mappings.json`（真源，供 T1 逐字段 diff） |
| T0.3 路由行为快照（140 条） | ✅ 完成 | `routing_snapshot.jsonl`（指纹 `2624a51be09b9d5e`） |
| T0.4 SSE 协议冻结 | ✅ 完成 | `sse_contract.json`（sha256 `866a6c6d…`） |

**未执行且现在也不得执行：T1 及任何路由映射修改。** 已按要求在 T0 结束时停止。

---

## 二、映射表冻结（T0.2）

真源：`legacy_mappings.json`（只读抽取自 5 个生产文件的**模块级/类级常量**，未合并、未改动）。

| 映射表 | 条目数 | 备注 |
|---|---|---|
| `INTENT_REGISTRY` | 11 个意图 | 意图注册真源 |
| `INTENT_CENTER_MAP` | 12 条 | 含 `unknown → auto`（仅中心登记，无注册意图） |
| `_CENTER_EXECUTION_ORDER` | 5 | auto1 / visualization2 / resource3 / exercise4 / plan5 |
| `RouterAgent.MODE_TO_INTENT` | 4 | plan/resource/exercise/visualization |
| `chat_center._KIND_TO_CENTER` | 4 | 兜底权威映射 |
| `_ON_TOKEN_MODES` | 2 | `[auto, exercise]` |
| `capability_gate._MODE_TO_KIND` | 4 | 显式模式 → 能力 |
| `capability_gate._CAPABILITY_RULES` | 7 | EXERCISE×3 / VISUALIZATION×2 / PLAN×1 / RESOURCE×1 |
| `intent_extractor._MUTEX_GROUPS` | 2 | 互斥对 |
| `intent_extractor._INTENT_PRIORITY` | 2 | visualize=10 / solve_problem=5 |

**记录在案的不一致点（只标记，未合并、未修）：**

1. **多张表表达同一映射**：`_KIND_TO_CENTER`（能力→中心）与 `_MODE_TO_KIND`（模式→能力，反向）语义重叠；同一「意图→中心」既出现在 `INTENT_CENTER_MAP`，又由 `RouterAgent.MODE_TO_INTENT` 与此二表间接复述 → 一处改动需同步四处。
2. **映射不完整**：`_MODE_TO_KIND` 仅 4 键，缺 `NORMAL_CHAT`；`INTENT_CENTER_MAP` 的 `unknown` 无对应注册意图（仅中心登记）。
3. **归向集中**：`auto` 收揽 5 个意图（tutor_question / solve_problem / diagnose / profile_building / unknown），是最大归口。
4. `_ON_TOKEN_MODES` 依赖 T0.1 记录的**未提交改动**（由 `{auto}` 扩为 `{auto, exercise}`）——基线即含此改动，T1 须以此为对照。

---

## 三、140 条用例结果（T0.3）

产物：`routing_snapshot.jsonl`，**140/140 有结果，0 异常，0 非确定**；指纹 `2624a51be09b9d5e`。
逐条走**真实入口** `ChatCenter.route()`，并独立记录 `CapabilityGate.decide()`。

**策略/路由分布：**

| 数量 | strategy / route |
|---|---|
| 87 | capability_gate / NORMAL_CHAT |
| 13 | keyword / EXERCISE |
| 10 | None / EXERCISE |
| 8 | keyword / VISUALIZATION |
| 7 | keyword / RESOURCE |
| 5 | None / VISUALIZATION |
| 3 | None / RESOURCE |
| 3 | None / PLAN |
| 3 | keyword / PLAN |
| 1 | empty_inquiry / None |

**分类分布**：多轮上下文与指代 20 / 普通概念答疑 15 / 明确生成练习题 15 / 隐式需求非标准表达 15 / 复合任务 15 / 解答已有题目 10 / 明确生成学习资源 10 / 学习规划 10 / 可视化 10 / 诊断与画像相关 10 / 否定表达·引用内容干扰 5 / 空输入·模糊请求缺参 5。

**记录到的不变式与偏差（仅记录真实旧行为，不做 Gold-Label 打分）：**

- 不变式 `route == gate.kind` 在 **139/140** 成立；唯一例外 **C136（空输入）→ `empty_inquiry`**。
- **gate 权威兜底**：21 条 `intent_meta` 无 `strategy` 键（`strategy=None`）→ 二级计划缺 gate 期望中心时，以显式 mode 重路由。
- `needs_confirmation` 为真：**0 条**。
- **多轮指代不被路由层利用**：20 条多轮用例中 19 条因上下文中性化塌缩为 NORMAL_CHAT，仅 1 条命中 VISUALIZATION（路由仅看单条 message）。
- 覆盖：128 条 `auto` + 12 条显式 `mode`（exercise/resource/plan/visualization 各 3）。

---

## 四、SSE 结果（T0.4）

产物：`sse_contract.json`（sha256 `866a6c6d47284753cdb07956d8f6e76da12aec464d7693c74e31b4d0cf9c224e`）。
探针用**测试替身**隔离 LLM/DB，驱动**真实入口** `ChatCenter.stream_chat()`；非确定正文只记结构（token 记字符数、payload 记键名/类型）。

**5 条链路（方案：in-process 双跑 + 跨进程复跑，全部确定）：**

| 链路 | route | 事件序列（折叠 token） | done 唯一 | error |
|---|---|---|---|---|
| 普通答疑 | NORMAL_CHAT | CENTER_START→PROGRESS×8→TOKEN×69→…→CENTER_END→CONTENT→DONE | ✅ | 0 |
| 生成练习 | EXERCISE | CENTER_START→PROGRESS×3→TOKEN×6→…→TOKEN×6→…→CONTENT→DONE | ✅ | 0 |
| 学习资源 | RESOURCE | CENTER_START→CENTER_END→CONTENT→DONE | ✅ | 0 |
| 学习规划 | PLAN（plan+resource 双任务） | CENTER_START→PROGRESS×6→CENTER_END→CONTENT→CENTER_START→CENTER_END→CONTENT→DONE | ✅ | 0 |
| 可视化 | VISUALIZATION | CENTER_START→PROGRESS×6→CENTER_END→CONTENT→DONE | ✅ | 0 |

**4 条终态合同（异常/提前终止，可编程 dispatcher 替身，全部确定）：**

| 用例 | 结果 | done 唯一 | error |
|---|---|---|---|
| 缺 done 补发 | TOKEN→DONE | ✅ | 0 |
| 多 done 收敛 | TOKEN→DONE | ✅ | 0 |
| 管线异常转 error | TOKEN→ERROR→DONE（msg="boom"） | ✅ | 1 |
| 追问不误判空正文 | INQUIRY→DONE（不补 error） | ✅ | 0 |

**字段结构契约（已冻结）**：CENTER_START/END `data={sequence}`；PROGRESS `data={node,phase}`；DONE 顶层 `{type,data}`（含 `results[]/summary/next_steps/profile_delta`）；CONTENT 按域不同（auto/resource 走 `response/content`；exercise 携带 `questions[]`；plan 携带 `steps/milestones/concept_graph`）。

**UNVERIFIED（离线不可验证，不伪造）**：
1. 真实 LLM 下的正文内容、token 切分粒度与真实超时文案。
2. 真实检索/DB 命中差异导致的知识点推荐事件（`recommendation` / `knowledge_candidates`）——本探针用空分组替身，未触发。
3. 真实网络下 `stream_chat` 的取消时序（`tests/test_chat_center_stream_contract.py::TestChatCenterStreamChatCancellation` 已覆盖逻辑层，但真实传输层未测）。
4. 观察到的旧行为：学习资源 / 可视化链路正文随 CONTENT 帧下发而非随 done 载荷，故「空正文补 error」安全网对这两域**不触发**——记录为旧行为，T1 需保真。

---

## 五、运行命令与基线版本

**基线版本**：分支 `for-work`，HEAD `24dd24db67259bc5951f87a46023b0c6560b6eba`（短 `24dd24d`）**+** 工作区未提交改动（`capability_gate.py` +17−0、`chat_task_dispatcher.py` +36−12）。二者共同锚定基线；缺一不可。

**关键文件 SHA-256（交接时复核一致，无漂移）：**
- `app/services/capability_gate.py` = `b1dca32ae8ef…d1bf00`
- `app/centers/chat_task_dispatcher.py` = `ce478c5c4f55…2cc42f`
- `app/centers/chat_center.py` = `70f208b08e2c…45fe8b`

**复现命令（在 `ai-service/` 下，中文控制台加 `PYTHONUTF8=1`）：**

```bash
# T0.2 映射冻结
PYTHONUTF8=1 python ../docs/agent-engineering/routing-baseline/t0_2_extract_mappings.py
# T0.3 路由快照（140 条，打印指纹）
PYTHONUTF8=1 python ../docs/agent-engineering/routing-baseline/probe_routing_snapshot.py
# T0.4 SSE 契约（5 链路 + 4 终态）
PYTHONUTF8=1 python ../docs/agent-engineering/routing-baseline/probe_sse_contract.py
```

**通过判据**：T0.3 打印 `cases: 140 errors: 0 nondeterministic: 0 fingerprint: 2624a51be09b9d5e`；T0.4 打印「全部链路 + 终态合同两次运行一致」，且 `sse_contract.json` sha256 = `866a6c6d…`。

---

## 六、T1 安全条件

T1 可在**且仅在**满足下列条件时开始：

1. **基线未漂移**：HEAD 仍为 `24dd24d`；工作区与第五节哈希一致（重算比对，任一不符即作废重采）。
2. **旧行为对照物就位**：`routing_snapshot.jsonl`（指纹 `2624a51be09b9d5e`）、`sse_contract.json`（sha256 `866a6c6d…`）、`legacy_mappings.json` 三者随 T1 提交一并保留，作为逐字段 diff 的「旧侧」。
3. **产物入库**：本目录全部探针与产物保留在仓库内（仅本 `T0-handoff.md` 交予用户）。
4. **生产路由代码在 T1 前保持零改动**：`capability_gate.py` / `chat_task_dispatcher.py` 的未提交改动在 T1 显式接管前不得被提交、还原或覆盖。
5. **保留旧错误**：T0.3 快照中记录的路由偏差（C136 空输入、21 条 gate 兜底、20 条多轮塌缩）仅作 **OLD-BEHAVIOR SNAPSHOT**，T1 不得以「修正」名义隐式改动，须显式评审。

---

## 摘要（≤300 字符）

T0 四子任务全完成，路由生产代码零改动。T0.1 锚定 HEAD `24dd24d`(for-work)+2 未提交改动；T0.2 冻结 10 张映射表(11 意图/12 中心)，标记 4 处不一致；T0.3 140 用例 0 异常 0 非确定，指纹 `2624a51be09b9d5e`，139/140 满足 route==gate.kind；T0.4 5 链路+4 终态合同全确定，sha256 `866a6c6d`。已停止，未执行 T1。
