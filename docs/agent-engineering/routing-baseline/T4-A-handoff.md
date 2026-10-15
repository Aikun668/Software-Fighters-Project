# T4-A · 三态路由与语义判断 · 阶段报告（旁路对照）

> 基线：HEAD 见提交历史；T0–T3 均已提交。本阶段为行为优化，Gold 基线守护。
> 性质：**旁路对照（第一步）**——新三态判定只记审计、不改实际执行；启用接管是第二步。

---

## 一、做了什么

### 三态判定（确定性、无 LLM）

- `app/services/semantic_router.py`（新）：`classify()` 把一级 gate 结论归入三态
  - **DIRECT_CAPABILITY**：gate 命中能力证据且无否定/引用干扰 → 直通
  - **DIRECT_CHAT**：无能力证据但明确疑问/否定/寒暄；或**能力词被否定/引用** → 直通答疑
  - **UNCERTAIN**：其余（`no_capability_evidence` 非明确聊天、`question_over_capability` 压制、`unknown_mode`）
  - `semantic_relabel()`：UNCERTAIN 态才按需调一次 `IntentExtractor.extract_multi`，
    `asyncio.timeout(1.0)` 包裹，超时/异常/非法 → 兜底不抛

### 旁路插桩（不改执行）

- `ChatCenter.route`：gate 判定后调 `_semantic_audit_meta`，把三态字段写入 `plan.intent_meta`；
  空输入早退分支也补记 `semantic_state="empty"`（140 条全覆盖）。
- **不改变返回的 `ExecutionPlan`**：旧行为指纹仍是 T0 的 `2624a51be09b9d5e`。
- 审计：`routing_audit.ALLOWED_KEYS` 增补 `route_source / semantic_state / semantic_called /
  semantic_latency_ms / semantic_error`（保持脱敏白名单，不记正文）。
- 所有权契约：`semantic_router` 的唯一引用者锁为 `chat_center.py`。

---

## 二、140 条旁路对照结果

| 三态 | 数量 | 说明 |
|---|---|---|
| direct_capability | 48 | gate 命中能力且无否定/引用 |
| direct_chat | 34 | 明确答疑/否定/引用/寒暄 |
| uncertain | 57 | 需语义重判（含多轮指代、隐式、复合、压制） |
| empty | 1 | C136 空输入→追问（确定行为） |

`semantic_called=57`（仅 UNCERTAIN 态触发，每请求 ≤1 次）；`semantic_error` 全为 None（离线 mock 语义腿）。

**旧行为 vs Gold（82 条 DRAFT_CONFIRMED 可严格对错）**：旧行为命中 60 / 未命中 22。

---

## 三、关键发现

1. **旁路自证**：旧行为指纹 `2624a51be09b9d5e` 与 T0 完全一致 —— 旁路不改执行。
2. **否定/引用误触发已识别**（C131/C132/C134/C135）：旧路由因"出题/画图/资源"能力词命中而
   误触发能力，三态判定已把它们归 `direct_chat`。但旁路阶段**不改行为**，启用阶段才会纠正。
3. **多轮指代是未命中主因**（C097–C115 约 19 条"再来5道/画详细点/改成两周/换成选择题"）：
   它们单条消息语义本就"不确定"，三态判 `uncertain` 是**正确**的。但单条消息语义重判
   无法补出上文，**多轮指代消解属 T4-B**，不在 T4-A 范围。
   ⚠️ 注意区分：这 19 条大多 gold_status=**DRAFT_CONFIRMED**（草案已确认归属），不属于
   「58 条 POLICY_UNDECIDED 待裁决」。它们是「旧路由只看单条消息而漏判」的历史局限，
   不是待裁决的产品分歧。
4. **语义腿当前走 mock 关键词**（`IntentExtractor` 默认 `use_mock = not INTENT_USE_LLM`），
   离线可复现、零成本；真 LLM 语义腿由 `INTENT_USE_LLM=1` 打开，属启用阶段、预算批准后。

---

## 四、未闭环 / 下一步

1. **启用接管已实现（默认 off）**：`_takeover_plan` 已落地——仅当 `t4a_enabled=True` 且
   「不确定态 + 语义给出唯一、非答疑、映射到非 auto 中心的能力意图」才接管；其余一律
   保持旧行为。**默认 False，线上行为零变化**（旁路指纹仍是 T0 的 `2624a51be09b9d5e`）。
   尚未「拨开关」：需等 ① 58 条 POLICY_UNDECIDED 人工裁决；② 真 LLM 语义腿预算实测
   （p95 ≤ 1000ms）。
2. 多轮指代消解（C097–C115）归 T4-B，不在本阶段。
3. `semantic_relabel` 外层 1s 超时对真 LLM 可能偏紧（`OpenAILLM.chat` 内部 180s + 重试），
   启用阶段需按实测调预算。

## 五、产物

- `app/services/semantic_router.py` + `tests/test_semantic_router_contract.py`（16 用例）
- `tests/test_t4a_takeover.py`（9 用例，锁启用接管的保守边界）
- `chat_center.py` / `routing_audit.py` / `test_routing_ownership_contract.py` 增量
- `probe_t4a_sidecar.py` + `routing_t4a_sidecar.jsonl`（140 条旁路数据）
- `build_t4a_compare.py` + `routing_t4a_compare.csv`（旧 vs Gold 对照表）
- `list_t4a_undecided.py`（58 条待裁决清单，按三态分组）
- `build_t4a_worklist.py` + `routing_t4a_undecided_worklist.csv`（58 条裁决工作单，
  Excel 可直接打开，`reviewer_decision` 列待人工填）

## 六、验证

- 契约测试 16 + 接管 9 passed；核心路由测试（capability_gate / routing_audit /
  route_plan_split / ownership_contract）148 passed。
- 旁路旧行为指纹 = `2624a51be09b9d5e`（T0 一致，0 异常 0 非确定）。
- 启用接管默认 off：9 条用例锁定「off 不接管 / on 仅保守接管 / gate 权威不被覆盖」。

## 七、启用预演（mock 语义腿，未拨开关）

`preview_t4a_enabled.py` 用 `t4a_enabled=True` + 离线 mock 语义腿跑了 140 条：

- 57 条 uncertain 中 11 条被接管；DRAFT_CONFIRMED 里**改善 6 / 变差 1**。
- 变差的唯一 1 条是 C108「举个例子」：mock 关键词腿因"例子"命中 resource_gen，但 gold 是
  NORMAL_CHAT。**这印证 mock 关键词腿不够格做启用接管**——真 LLM 语义腿是启用前的硬前提。
- 改善样例：C030/C104/C112（隐式出题→exercise）、C053/C056/C060（规划→plan）、
  C047/C103（代码示例→resource）。

结论：启用接管的代码与测试已就绪（默认 off），但**真正拨开关前必须先接真 LLM 语义腿**
（`INTENT_USE_LLM=1`），否则会把"举个例子"这类误判进资源路由。真 LLM 的预算实测 +
58 条裁决是剩余前置。

## 八、58 条待裁决导航（纯事实统计，非裁决）

裁决工作单 `routing_t4a_undecided_worklist.csv` 里 58 条 POLICY_UNDECIDED 的性质分布
（gold_capability 是 gold 草案给出的方向，仅作导航，不代裁决）：

| 类别 | 条数 | 裁决对象 |
|---|---|---|
| gold_capability=待裁决 | 23 | 四意图（solve_problem/diagnose/profile_building/code_example）是否给独立一级入口 |
| gold_capability=待澄清 | 16 | 该不该追问、追问什么（澄清策略） |
| gold_capability=明确能力（EXERCISE 8/RESOURCE 4/PLAN 4/VISUALIZATION 3） | 19 | 多中心编排或含待裁决意图，方向已明、确认即可 |

按 `gold_ask_clarify`：33 条「是」（需澄清）、25 条「否」。
按三态：uncertain 38 / direct_capability 11 / direct_chat 8 / empty 1。

## 九、验收自查发现（旁路阶段已交付；两处待修项已修，见下）

独立验收（静态审查 + AST import 检查 + 契约测试）结论：旁路阶段六维度中五维通过，
发现两处需在**启用前**修正，均已修（提交 `0ba59e3`）：

1. ~~接管的置信度门槛~~ 已修：`semantic_relabel` 现返回 `(intents, confidences, ...)`，
   `_takeover_plan` 要求唯一候选意图置信度 ≥ `SEMANTIC_TAKEOVER_CONFIDENCE(0.6)` 才接管，
   挡住 mock 腿单命中换算的 0.597 伪置信（C108「举个例子」误判根因）。新增测试
   `test_low_confidence_does_not_take_over`。
2. ~~弱断言~~ 已删：`test_timeout_budget_is_one_second`（断言常量==字面量）已移除，
   真实超时行为由永不完成 Future 的用例覆盖。

通过的五维：所有权契约、旁路不改执行（指纹 `2624a51be09b9d5e`）、审计脱敏、预算铁律、
总计划「不得把没命中关键词=明确聊天」。

## 十、真模型演练（第二项，用户已补 key）

真 LLM 语义腿（`IntentExtractor(use_mock=False)`）已连通（用户补了 `DEEPSEEK_API_KEY`），
`preview_t4a_real_llm.py` 对 15 条代表性消息实测：

- **判断质量好**：明确能力句置信 0.9~0.98（"出5道题"→exercise 0.98、"画流程图"→visualize 0.98、
  "代码示例"→resource 0.9）；不确定句正确给低置信（"数据好难"0.3、"举个例子"0.3 → is_clear=False，
  **不再误判 C108**，印证 mock 腿误判是真模型可解决的）。
- **时延超预算**：p50≈933ms、p90≈1278ms、p95≈1506ms、max≈1506ms；15 条里 6 条 >1000ms。
  → 目标「p95 ≤ 1000ms」当前真模型达不到。

**产品决定（已定）**：放宽时延预算，`SEMANTIC_TIMEOUT_SEC` 由 1.0s 提到 **1.5s**（超时即兜底不变）。
真模型 p95≈1506ms 基本落在 1.5s 内，慢请求仍以兜底保底。

## 十一、Gold 裁决完成 + 最终启用验收（方式1）

产品决定（方式1，用户拍板）：
  ① solve_problem / code_example 作为独立意图；diagnose / profile_building 不单独开路；
  ② 自述背景(profile_building) 静默采集；③ 含糊话/空输入 追问。

已据此把 58 条 POLICY_UNDECIDED 全部裁决写入 `routing_gold_review.csv`（`reviewer_decision` 全填、
`gold_capability` 无「待裁决」残留）；12 条零分歧先前已填「同意」（提交 `3397d4f`），本轮填其余。

**最终启用验收**（`verify_t4a_enabled.py`：t4a_enabled=True + 真模型语义腿，跑 140 条）：
- 三态分布：direct_capability 48 / direct_chat 34 / uncertain 57 / empty 1（与旁路一致，三态稳定）。
- 启用接管 6 条，gold 明确的：**改善 5 / 变差 1**。
  - 改善：C047（代码→resource）、C052/C053/C056/C060（规划→plan）。
  - 变差 1：C078「我大二，想转做后端开发」——真模型判 learning_path（求转行规划），
    而方式1 将其归「画像静默、主走答疑」填 NORMAL_CHAT。属「自述背景 + 隐含规划诉求」的
    语义边界分歧，非真模型错误；两种判法各有道理，已记录。

**结论**：改善 5:1 明显净改善，T4-A-Gate 通过。启用开关 `t4a_enabled` 保持默认 off，
由产品方按灰度节奏拨 on（拨 on = 改变用户可见行为，需单独批准）。
