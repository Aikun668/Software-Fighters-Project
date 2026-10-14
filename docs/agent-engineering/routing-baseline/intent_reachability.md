# 意图可达性核查报告（intent_reachability.md）

> **任务**：Stage 0.2 · 任务 A「检查意图可达性」
> **产出人**：Coding Agent A（Python AI 服务）
> **核查日期**：2026-10-13
> **方法**：**只读探针**，调用真实路由入口 `ChatCenter.route()`，不触发任何生成任务、不写库、不改规则。
> **探针脚本**：`docs/agent-engineering/routing-baseline/probe_intent_reachability.py`
> **复现命令**：`cd ai-service && PYTHONUTF8=1 python ../docs/agent-engineering/routing-baseline/probe_intent_reachability.py`
> **体例**：`[事实]` = 源码逐行核对 / 实测输出；`[推测]` = 需后续验证

---

## 0. 结论速览

- `[事实]` **11 条注册意图全部可达（REACHABLE）**，无一绝对不可达。
- `[事实]` 但可达性分成**两档**：
  - **7 条「正常可达」**：单意图的日常表达即可命中（tutor_question / exercise_gen / resource_gen / learning_path / flashcard_gen / visualize / knowledge_graph）。
  - **4 条「条件可达」**：**无法**用干净的单意图表达命中，**必须**把请求包装进一个同时触发能力词（RESOURCE / PLAN / EXERCISE）的**复合句**，才有机会进入二级路由（code_example / solve_problem / diagnose / profile_building）。
- `[事实]` 关键机制：**一级 `CapabilityGate` 是全链路咽喉**。二级 `RouterAgent` 只在 gate 判为非 `NORMAL_CHAT` 时才被调用（`chat_center.py:170` 早返回 + `:197` 才进二级）。凡是没有专属能力规则的意图，都只能「搭车」进入二级。
- `[事实]` 另有**一级权威兜底**（`chat_center.py:204-214`）：二级结果若不含 gate 判定的中心，会被**显式 mode 重建的计划整体覆盖**——这是「条件可达」意图的第二重脆弱点。

---

## 1. 核查方法说明（含一次方法论修正）

`[事实]` **初版探针曾误报 `tutor_question` 不可达**。原因：初版只调 `CapabilityGate.decide()` + `RouterAgent.route()`，把 `NORMAL_CHAT` 一律记为 `intents=[]`。但**真实入口** `ChatCenter.route()` 在 `NORMAL_CHAT` 分支会**直接构造 `tutor_question` 单任务计划**（`chat_center.py:170-195`）。因此：

- **必须走真实入口 `ChatCenter.route()`** 才能得到正确的可达性结论；
- 修正后 `tutor_question` 变为**默认路径**（任何无能力证据的消息都落入它）。

`[事实]` `ChatCenter.route()` 的 route 分支**只构造 `CapabilityGate`（纯正则）+ `RouterAgent`（纯关键词）**，**不构造 dispatcher / Agent / LLM**（`chat_center.py:75-83`，`_get_dispatcher` 仅在 `execute()` 中调用）。故探针**无 IO、无 LLM、可反复运行**，符合「只读」约束。

---

## 2. 11 条注册意图可达性总表

来源：`INTENT_REGISTRY`（`intent_extractor.py:164-260`，11 条）+ `INTENT_CENTER_MAP`（`:31-44`）。

| # | intent | center | 可达性 | 通道 | 最小复现输入（实测 OK） |
|---|---|---|---|---|---|
| 1 | `tutor_question` | `auto` | ✅ 正常 | **默认路径**：gate=NORMAL_CHAT 早返回注入 | `什么是进程` |
| 2 | `exercise_gen` | `exercise` | ✅ 正常 | gate=EXERCISE → 二级关键词 | `出5道题` / `帮我生成练习题` |
| 3 | `resource_gen` | `resource` | ✅ 正常 | gate=RESOURCE → 二级关键词 | `帮我找几个学习资源` / `生成一份讲义` |
| 4 | `learning_path` | `plan` | ✅ 正常 | gate=PLAN → 二级关键词 | `帮我制定一个学习计划` |
| 5 | `flashcard_gen` | `resource` | ✅ 正常 | gate=RESOURCE → 二级关键词 | `帮我生成闪卡` |
| 6 | `visualize` | `visualization` | ✅ 正常 | gate=VISUALIZATION → 二级关键词 | `画一张TCP三次握手流程图` |
| 7 | `knowledge_graph` | `visualization` | ✅ 正常 | gate=VISUALIZATION → 二级关键词 | `帮我生成知识图谱` |
| 8 | `code_example` | `resource` | ⚠️ **条件可达** | 需 gate=RESOURCE（靠产物词「教程/文档/讲义/资料」）→ 二级关键词 | `推荐一些代码示例的教程` |
| 9 | `solve_problem` | `auto` | ⚠️ **条件可达** | 需 gate=PLAN/RESOURCE（**不能**是 EXERCISE）→ 二级关键词 | `帮我解这道题并制定一个复习计划` |
| 10 | `diagnose` | `auto` | ⚠️ **条件可达** | 需 gate=EXERCISE → 二级关键词（且 `exercise_gen` 同在） | `出几道题测试一下我的掌握` |
| 11 | `profile_building` | `auto` | ⚠️ **条件可达** | 需 gate=PLAN/RESOURCE → 二级关键词 | `我是零基础，帮我制定一个学习计划` |

> ⚠️ 「条件可达」= 该意图**不存在**能单独命中它的用户表达；是否可达**取决于用户如何措辞包装**，而非用户真实诉求。

---

## 3. 逐条核查明细

### 3.1 `tutor_question`（center=auto）— 默认路径

- **一级 gate**：任何**不**命中能力规则的消息都判 `NORMAL_CHAT`（`capability_gate.py:178-184` `no_capability_evidence`）。
- **注入点**：`chat_center.py:170-195` —— `NORMAL_CHAT` 分支直接构造 `CenterTask(intent="tutor_question", mode="auto")`，**不进二级**。
- **实测**：`什么是进程` → `strategy=capability_gate route=NORMAL_CHAT intents=['tutor_question']`。
- `[事实]` **这是全系统「漏斗底」**：一切未被能力规则捕获的输入都落在这里，包括本应属于 code_example / solve_problem / diagnose / profile_building 的**干净单意图表达**（见 §3.8-3.11）。

### 3.2 `exercise_gen`（center=exercise）— 正常可达

- **一级 gate**：`_CAPABILITY_RULES` 第 1-3 条（`capability_gate.py:70-103`）→ `EXERCISE`。`verb_count_exercise`（数量词+道）/**`verb_set_exercise`**（一套/几道）/`verb_topic_exercise`（动词+题型产物，无数量词要求，工作区未提交新增）。
- **二级命中共现**：`_keyword_route` 找出 `exercise_gen`（`keywords` 含 题/练习/选择题…）。
- **gate 兜底**：gate=EXERCISE → expected_center=`exercise` → 二级结果含 `mode=exercise` 的任务即存活。
- **实测**：`出5道题` → `route=EXERCISE intents=['exercise_gen']`；`来几道英语选择题` → `intents=['exercise_gen']`。

### 3.3 `resource_gen`（center=resource）— 正常可达

- **一级 gate**：`request_material`（`capability_gate.py:134-142`）需「祈使/整理动词 + 资料类产物（资源/资料/讲义/教程/…）」。注意动词表 = `帮我|给我|请|生成|整理|推荐|提供`（**不含「做」**）。
- **实测**：`帮我找几个学习资源` / `生成一份讲义` / `推荐一些学习资料` 均 → `route=RESOURCE intents=['resource_gen']`。

### 3.4 `learning_path`（center=plan）— 正常可达

- **一级 gate**：`make_plan`（`capability_gate.py:125-132`）：「制定/规划/安排/生成/设计/做 + 计划/路径/路线/日程」。
- **实测**：`帮我制定一个学习计划` → `route=PLAN intents=['learning_path']`。

### 3.5 `flashcard_gen`（center=resource）— 正常可达（含一处 gate 误拒）

- **一级 gate**：靠 `request_material` 的产物词「闪卡/记忆卡/卡片」。
- **实测（可达）**：`帮我生成闪卡` → `route=RESOURCE intents=['flashcard_gen']`。
- **实测（误拒）**：`做几张记忆卡背诵` → `gate=NORMAL_CHAT intents=['tutor_question']`。
  - `[事实]` 根因：`做` **不在** `request_material` 的动词白名单内（`capability_gate.py:138`），故 gate 不认 → 回落 NORMAL_CHAT → tutor_question。此为**一级漏检（false-negative）**。

### 3.6 `visualize`（center=visualization）— 正常可达

- **一级 gate**：`draw_diagram`（`capability_gate.py:105-114`）：「画/绘制/生成/做 + 图类产物」。
- **实测**：`画一张TCP三次握手流程图` / `绘制一个架构图` → `route=VISUALIZATION intents=['visualize']`。
- **观察**：`帮我做个思维导图` → `intents=['visualize']`，但 `strategy=None`（进入 gate 权威重建路径，见 §4.2）。

### 3.7 `knowledge_graph`（center=visualization）— 正常可达

- **一级 gate**：`draw_diagram` **或** `knowledge_graph_request`（`:116-123`，动词 + 知识图谱/图谱）。
- **实测**：`帮我生成知识图谱`（命中 `draw_diagram`）/ `看看我的知识图谱`（命中 `knowledge_graph_request`）→ `intents=['knowledge_graph']`。

### 3.8 `code_example`（center=resource）— ⚠️ 条件可达

- **一级 gate**：**无专属规则**。`给我一个代码示例` / `写一个Python的例子` / `快速排序怎么实现` 均 → `gate=NORMAL_CHAT intents=['tutor_question']`（`no_capability_evidence`）。
- **可达条件**：消息须**额外含** `request_material` 的产物词，例如 `教程/文档/讲义/资料`，把 gate 抬到 `RESOURCE`，二级才有机会。
- **最小复现**：`推荐一些代码示例的教程` → `route=RESOURCE intents=['code_example', 'resource_gen']`。
  - 存活原因：`code_example` 与 `resource_gen` 的 center 同为 `resource`，满足 gate 权威（expected_center=resource 在场）。
- **风险**：真实用户多半直接说「给我个代码示例」，此时**永不进入 code_example**，被当成答疑（tutor_question）处理。

### 3.9 `solve_problem`（center=auto）— ⚠️ 条件可达（最难）

- **一级 gate**：**无专属规则**。`帮我解这道题` / `求解这个方程` / `推导一下这个公式` 均 → `NORMAL_CHAT intents=['tutor_question']`。
  - `[事实]` 补充：`帮我做这道题` 因 `verb_topic_exercise` 的负向断言 `(?<!这道)(?<!那道)(?<!该)`（`capability_gate.py:99`）被**有意排除**，故也不进 EXERCISE。设计意图是「解现有题≠出题」。
- **可达条件**：须**额外含** PLAN 或 RESOURCE 的产物词；**且不能**被 EXERCISE 捕获（否则 `{solve_problem, exercise_gen}` 互斥组会把 solve_problem 挤掉）。
- **最小复现**：`帮我解这道题并制定一个复习计划` → `route=PLAN intents=['solve_problem', 'learning_path']`。
  - 存活原因：gate=PLAN（expected_center=plan，learning_path 在场）→ 二级含 `mode=auto` 的 solve_problem 未被覆盖。
- **反例（被互斥杀死）**：`帮我解这道计算题，另外生成一份讲义` → `route=EXERCISE intents=['exercise_gen']`（`verb_topic_exercise` 命中 → 互斥保留 exercise_gen，solve_problem 出局）。

### 3.10 `diagnose`（center=auto）— ⚠️ 条件可达

- **一级 gate**：**无专属规则**。`帮我做个诊断` / `测试一下我的掌握情况` / `测一下我哪里薄弱` 均 → `NORMAL_CHAT intents=['tutor_question']`。
- **可达条件**：须**额外含** EXERCISE 触发词（出题/练习题/一套题…）把 gate 抬到 `EXERCISE`。
- **最小复现**：`出几道题测试一下我的掌握` → `route=EXERCISE intents=['diagnose', 'exercise_gen']`。
  - 存活原因：diagnose key 命中「测试」+「掌握」= 2 命中 → `0.75×0.8=0.6`，且 `mode=auto`。
- **反例（分数不足被滤）**：`来一套题检查一下我的水平` → `intents=['exercise_gen']`（diagnose 仅「检查一下」单命中 `0.5×0.8=0.4`，边界未过）。
- **反例（互斥杀死）**：`帮我做个诊断，出5道题` 类表达会触发互斥组 `{solve_problem, exercise_gen}` 邻近机制，diagnose 易被降权/过滤。

### 3.11 `profile_building`（center=auto）— ⚠️ 条件可达

- **一级 gate**：**无专属规则**。`我是零基础新手` / `我的基础比较差，想学AI` / `我刚开始学，有点迷茫` 均 → `NORMAL_CHAT intents=['tutor_question']`。
- **可达条件**：须**额外含** PLAN 或 RESOURCE 的产物词。
- **最小复现**：`我是零基础，帮我制定一个学习计划` → `route=PLAN intents=['learning_path', 'profile_building']`。
- **风险**：用户「介绍自己基础」的自然表达（画像构建的典型入口）**几乎必然**落在 tutor_question，画像意图基本不可达。

---

## 4. 结构性发现（任务 A 的核心价值）

### 4.1 【咽喉】一级 gate 是全链路单点

`[事实]` `chat_center.py:170` 的 `NORMAL_CHAT` 早返回 + `:197` 才进二级 ⇒ **二级路由的 11 条意图全部受一级 gate 支配**。凡意图对应 center 未映射到某个 `CapabilityKind`（即 center=`auto` 且无能力规则），即**天然不可由干净表达直接进入**。

### 4.2 【覆盖】一级权威兜底会整体覆盖二级

`[事实]` `chat_center.py:204-214`：`expected_center` 不在二级结果内时，以显式 mode（`decision.kind.value.lower()`）**重建单任务计划**，丢弃二级全部产出。实测触发样本：`帮我做个思维导图`、`出5道题` → `strategy=None`。对「条件可达」意图这是**第二重脆弱点**。

### 4.3 【互斥】`{solve_problem, exercise_gen}` 会吞掉 solve_problem

`[事实]` `_MUTEX_GROUPS`（`intent_extractor.py:300-303`）+ `_INTENT_PRIORITY`（solve_problem=5）。凡消息同时含解题词与出题词（且被 gate 判 EXERCISE），solve_problem 恒被降权出局（见 §3.9 反例）。

### 4.4 【漏检】一级 gate 动词白名单过窄

`[事实]` `request_material` 动词白名单不含「做」（`:138`），导致 `做几张记忆卡背诵` 被判 NORMAL_CHAT。类似地，`draw_diagram` 动词表含「做」，但产物词固定，语义外延有限。

### 4.5 【阈值】diagnose 单命中过不了 0.4 门槛

`[事实]` diagnose 需 **≥2 个关键词命中**（`0.5×0.8=0.4` 为边界、实际被滤；`0.75×0.8=0.6` 才稳）才存活。单命中表达（「检查一下」）会被 `_CONFIDENCE_THRESHOLD=0.4` 滤掉。

---

## 5. 对 Stage 1+ 的提示（**不改代码，仅记录**）

> 以下为**观察结论**，非改法；供外部架构师评审 Stage 1 方案时参考。

1. `[事实]` **`center=auto` 的 4 条意图中，3 条（solve_problem/diagnose/profile_building）属「业务域明确但一级无入口」**——它们的产出手工构造依赖复合句，日常表达不可达。这是「用户真实诉求 ≠ 系统识别结果」的高发区。
2. `[事实]` `code_example` 虽 center=`resource`（有中心兜底），但**一级无专属规则**，仍须搭 RESOURCE 产物词的车。
3. `[推测]` 上述现象可解释历史反馈中的「隐式需求识别弱 / 组合任务处理弱」——根源在**一级 gate 的产物词表覆盖不足 + 二级入口受一级支配**，而非二级打分本身。
4. `[事实]` 本轮**未改动** `CapabilityGate` / `RouterAgent` 任何规则；探针纯只读。工作区路由文件哈希与基线记录一致（见 `baseline_workspace_record.md` §3）。

---

## 6. 附：探针实测原始输出（摘要）

```
REACHABLE   (11): ['exercise_gen', 'resource_gen', 'code_example', 'tutor_question',
                   'learning_path', 'solve_problem', 'flashcard_gen', 'visualize',
                   'knowledge_graph', 'diagnose', 'profile_building']
UNREACHABLE (0): []

显式 mode 门验证（均 1.0 置信直通）：
  mode=plan           '随便安排点东西' -> route=PLAN          intents=['learning_path']
  mode=resource       '给我一些材料'   -> route=RESOURCE      intents=['resource_gen']
  mode=exercise       '来一题'         -> route=EXERCISE      intents=['exercise_gen']
  mode=visualization  '做个图'         -> route=VISUALIZATION intents=['visualize']
```

`[事实]` **显式 mode 是绕过一级 gate 的确定性通道**：只要 `mode != auto`，`_MODE_TO_KIND` 直接放行（`capability_gate.py:156-163`，置信 1.0），再经 `_manual_mode_plan` 直达单意图。**这是任务 B「≥10 条显式 mode 样本」的机制依据**。
