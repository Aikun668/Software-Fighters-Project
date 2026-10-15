# T4-A · 三态路由与语义判断 · 专用编码任务书

> 阶段性质：**行为优化**（唯一允许改路由行为的阶段，需 Gold 基线守护）
> 前置决定（已拍板）：Gold Label 按方案 (b)；预算 = 每请求最多 1 次语义 LLM、p95 ≤ 1000ms、超时兜底；分两步「旁路对照 → 小开关启用」。
> 约束：本任务书只覆盖 T4-A；CONFIRM 阻断已归 T4-B，不在本阶段。

---

## 0. 目标与边界

**目标**：把「明确普通聊天 / 明确专用能力 / 无法可靠判断」三态落地。只让第三态进入按需语义判断；旁路阶段新判断**只记审计、不改实际执行**。

**边界（本阶段不做）**：
- 不做 CONFIRM 阻断（T4-B）
- 不做复合任务多中心编排（T4-B）
- 不做 flashcard_gen / adjust_plan 闭环（T4-C）
- 不把全部路由交给 LLM；不让语义模型直接改画像/库
- 不改 Java 持久化、不改 SSE 终态契约

---

## 1. 三态定义

| 态 | 判据（规则可直通） | 走哪 |
|---|---|---|
| **直通·明确能力** | 一级 `CapabilityGate` 命中能力规则（`capability_evidence:*` / `explicit_mode:*`）且**非** `question_over_capability` 压制 | 现有 RouterAgent 关键词路径，不变 |
| **直通·明确聊天** | 满足「明确否定」或「明确答疑句式」且**无**能力证据 | 现有 NORMAL_CHAT 路径，不变 |
| **不确定** | 其余（`no_capability_evidence` 且非明确聊天；`question_over_capability` 压制；`unknown_mode`） | 语义判断（按需 LLM） |

> 关键修正：把 `CapabilityGate.decide` 里 `no_capability_evidence → NORMAL_CHAT` 的「默认答疑」从"最终结论"降级为"候选"，只在三态层确认"明确聊天"后才直通答疑，否则进语义判断。**禁止**把"没命中关键词"直接等于"明确普通聊天"（总计划 T4-A 第 2 条）。

---

## 2. 代码落点（尊重所有权契约）

- 新增 `app/services/semantic_router.py`（纯判定服务，无业务 import）：
  - 输入：`message`、`gate_decision`（由 ChatCenter 当参数传入，**不 import capability_gate**）、`student_profile`、`context`
  - 输出：`SemanticDecision`（`state: DIRECT_CAPABILITY | DIRECT_CHAT | UNCERTAIN`、`route_source`、`latency_ms`、`error`、`candidates`）
  - 内部：语义调用复用 `IntentExtractor.extract_multi`（已存在、未接入线上）；`asyncio.timeout` 包一层，超时/异常 → 安全兜底（保持原 NORMAL_CHAT 行为）
- 改 `ChatCenter.route`：在 gate 判定后插入 `SemanticRouter` 调用（**旁路模式**：只把结果写进 `plan.intent_meta` 的审计字段，不改变返回的 plan）
- 审计：`routing_audit.py` 的 `ALLOWED_KEYS` 增补 `route_source` / `semantic_called` / `semantic_latency_ms` / `semantic_error` 四字段（保持脱敏白名单，只记元数据不记正文）

### 所有权契约变更（显式、自觉）

`test_routing_ownership_contract.py` 当前把 `capability_gate`/`router_agent` 的引用者钉为 `{chat_center.py}`。本阶段不破坏它（semantic_router 不 import 那两者），但需在 `DECISION_MODULE_OWNERS` 里新增一条：`app.services.semantic_router` 的唯一引用者是 `app/centers/chat_center.py`。这是**契约随新决策点同步演进**，不是破坏。

---

## 3. 预算与安全兜底（本阶段铁律）

- 语义 LLM：**每请求最多 1 次**，仅当三态判为 `UNCERTAIN` 时才调
- 超时：`SEMANTIC_TIMEOUT_SEC = 1.0`（p95 ≤ 1000ms 的硬上限；超时即兜底）
- 失败/模型不可用/输出非法 → 兜底到「原行为」：`no_capability_evidence` 走 NORMAL_CHAT，`question_over_capability` 走 NORMAL_CHAT，`unknown_mode` 走 NORMAL_CHAT
- 语义结果**必须**交给现有 PlanBuilder 校验（无效意图一律丢弃），不得直接造高成本产物（总计划 T4-A 第 4 条）
- 旁路开关：`T4A_ENABLED`（默认 `off`，旁路记录 / `on` 才接管路由）。环境变量 + 构造参数双入口。

---

## 4. 实施步骤（每步独立可验、可回滚）

1. **契约先行**：新增 `test_semantic_router_contract.py`（失败测试），锁定：
   - 三态判据（明确能力直通、明确聊天直通、不确定→UNCERTAIN）
   - 旁路模式不改实际 plan（新旧指纹一致）
   - 每请求 ≤1 次语义调用；超时/异常兜底不改行为
   - 审计字段存在且不泄露正文
2. 实现 `semantic_router.py`（最小可用：三态 + 超时兜底，语义腿先接 IntentExtractor）
3. 改 `ChatCenter.route` 插桩（旁路），改 `routing_audit` 白名单
4. 更新所有权契约测试（加 semantic_router 条目）
5. **旁路验收**：跑 140 条 Gold 出「旧 vs 新」对照表（旁路不影响执行，先证明语义腿可达、可解释、可兜底）
6. **启用验收**：`T4A_ENABLED=on` 后重跑 140 条，只允许「不确定→语义」这类的路由变化，明确聊天/明确能力不得被误触发

---

## 5. 验收 Gate（T4-A-Gate 对齐）

- [ ] 明确能力仍低延迟直通（不额外调 LLM）
- [ ] 明确聊天仍直通，误触发无不可接受增加（对照表数字说话）
- [ ] 每条路由可解释：`route_source ∈ {rule, semantic, fallback}` 且可回溯版本/输入依据
- [ ] 模型失败/超时不会错乱执行（兜底 + 审计 error 字段）
- [ ] 时延与费用在预算内：每请求 ≤1 次语义调用、p95 ≤ 1000ms

---

## 6. 交付物

- `semantic_router.py` + `test_semantic_router_contract.py`
- 更新的 `chat_center.py` / `routing_audit.py` / 所有权契约测试
- `docs/agent-engineering/routing-baseline/T4-A-handoff.md`（含旧 vs 新对照表）
- 简短对话交接摘要
