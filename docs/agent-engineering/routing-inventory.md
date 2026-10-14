# 现有路由调查报告（routing_inventory.md）

> **任务**：Stage 0 · Task 0.1「现有路由调查」
> **产出人**：Coding Agent A（Python AI 服务）
> **调查日期**：2026-10-13
> **结论基线**：分支 `for-work`，HEAD `24dd24d`，**含工作区未提交改动**（见 §7）
> **体例约定**：`[事实]` = 已从源码逐行核对；`[推测]` = 需后续验证；`[存疑]` = 与口头描述不符，需外部确认
> **本文用途**：交接给外部架构评审方（Handoff Node A）。所有结论均绑定文件路径 + 函数/行号。

---

## 0. 一句话总览

用户消息进入 Python 后，**统一入口**是 `ChatCenter.stream_chat() → ChatCenter.route()`；
`route()` 内部先过 **一级守门员 `CapabilityGate.decide()`**（纯正则、无 LLM）：

- 若判为 `NORMAL_CHAT` → **直接构造 tutor_question 单任务计划返回**，**不进入二级路由**；
- 若判为专项能力（PLAN/RESOURCE/EXERCISE/VISUALIZATION）→ 交给 **二级 `RouterAgent.route()`**（关键词打分、无 LLM）产出 `ExecutionPlan`，再由 `ChatTaskDispatcher` 分发到对应 Center/Agent。

**两条路由决策都只读「消息正文 + mode」，不读历史/画像/上下文。** 历史与画像只在下游 LLM 执行层被消费。

---

## 1. 路由核心代码真实位置（任务 0.1 第 1 点）

| 组件 | 真实路径 | 关键符号 | 行号 |
|---|---|---|---|
| **统一入口** | `ai-service/internal_api/chat.py` | `unified_chat` / `_unified_chat` | `:17-19`, `:22-62` |
| **编排中心** | `ai-service/app/centers/chat_center.py` | `ChatCenter.route` / `stream_chat` / `execute` | `:142-221`, `:285-...`, `:223-252` |
| **一级守门员** | `ai-service/app/services/capability_gate.py` | `CapabilityGate.decide` / `_CAPABILITY_RULES` / `CapabilityKind` | `:149-204`, `:26-31`, `:68-143` |
| **二级路由** | `ai-service/app/centers/router_agent.py` | `RouterAgent.route` / `_keyword_route` / `_manual_mode_plan` | `:57-117`, `:119-187`, `:189-210` |
| **意图注册表** | `ai-service/app/services/intent_extractor.py` | `INTENT_REGISTRY` / `_score_intent` | `:164-260`, `:320-338` |
| **意图↔中心映射** | 同上 | `INTENT_CENTER_MAP` / `_CENTER_EXECUTION_ORDER` / `_INTENT_PRIORITY` / `_MUTEX_GROUPS` | `:31-44`, `:46-52`, `:295-298`, `:300-303` |
| **数据契约** | `ai-service/app/centers/schemas.py` | `CenterTask` / `ExecutionPlan` | `:全文 48 行` |
| **能力→中心映射** | `ai-service/app/centers/chat_center.py` | `_KIND_TO_CENTER` | `:46-51` |
| **分发到 Center** | `ai-service/app/centers/chat_task_dispatcher.py` | `ChatTaskDispatcher.execute` / `_center_for` | 见 §3 |
| **路由审计** | `ai-service/app/services/routing_audit.py` | `build_routing_record` / `emit_routing_record` | 见 §3 |

> `[事实]` 传参说明：**没有名为 `history` 的独立路由入参**。历史通过 `context["messages"]` 传入（`stream_chat` 在 `chat_center.py:312` 组装：`history + [{"role":"user","content":message}]`）。

---

## 2. 真实调用链（任务 0.1 第 2 点）

```
HTTP: POST /api/chat
  └─ internal_api/chat.py:18  unified_chat(body)               [协议适配层]
       └─ internal_api/chat.py:38  ChatCenter.stream_chat(
              message, history=body.messages, mode=body.mode,
              student_profile=body.student_profile, ...)
            └─ chat_center.py:285 stream_chat()
                 ├─ :312 组装 messages = history + [current]  → context["messages"]
                 ├─ :320 route(message, mode, student_profile, context)
                 │    └─ chat_center.py:142 ChatCenter.route()
                 │         ├─ [空消息] :150 → RouterAgent.route() → empty_inquiry
                 │         ├─ :162 CapabilityGate.decide(message, mode, profile, ctx)
                 │         │        capability_gate.py:149  ← 【一级判定，纯正则】
                 │         │
                 │         ├─ :170 if kind is NORMAL_CHAT:
                 │         │      → 直接构造 CenterTask(intent="tutor_question")   ← 【提前返回，不进二级】
                 │         │      → return ExecutionPlan(strategy="capability_gate")
                 │         │
                 │         └─ else: RouterAgent.route(...)     ← 【仅专项能力才到这】
                 │              router_agent.py:57
                 │                ├─ [mode!=auto] :84 _manual_mode_plan()
                 │                ├─ [空] :68 fallback
                 │                └─ :87 _keyword_route()  → INTENT_REGISTRY 打分
                 │                     :119 → _score_intent × 11 意图
                 │                     :134 按分排序 → :146 问题 checkpoint 注入 tutor
                 │                     :157 互斥过滤 → :168 置信度过滤
                 │                     → 每意图 → CenterTask
                 │              ↳ 回到 chat_center.py:204
                 │                :205 gate 判定的中心若未被命中 → 用显式 mode 重建计划（gate 权威兜底）
                 │                :216 update intent_meta（route / route_reason / audit_meta）
                 │
                 └─ :320xx ChatTaskDispatcher.execute(plan)
                        └─ chat_task_dispatcher.py 按 mode → 对应 Center → Agent → SSE 事件流
```

**关键分叉点**：`chat_center.py:170`。`NORMAL_CHAT` 在此**短路返回**，二级 `RouterAgent` 完全不被调用。

---

## 3. 能力 / 意图 / Center 三层映射（任务 0.1 第 3 点）

### 3.1 一级：`CapabilityKind`（5 值）

`capability_gate.py:26-31`：`NORMAL_CHAT` / `PLAN` / `RESOURCE` / `EXERCISE` / `VISUALIZATION`

### 3.2 能力 → Center（`chat_center.py:46-51`）

| CapabilityKind | Center |
|---|---|
| PLAN | `plan` |
| RESOURCE | `resource` |
| EXERCISE | `exercise` |
| VISUALIZATION | `visualization` |
| NORMAL_CHAT | （不进分发，直接 tutor_question） |

### 3.3 二级：意图 → Center（`intent_extractor.py:31-44` `INTENT_CENTER_MAP`）

| intent | center | | intent | center |
|---|---|---|---|---|
| tutor_question | `auto` | | visualize | `visualization` |
| solve_problem | `auto` | | knowledge_graph | `visualization` |
| diagnose | `auto` | | flashcard_gen | `resource` |
| learning_path | `plan` | | profile_building | `auto` |
| exercise_gen | `exercise` | | unknown | `auto` |
| resource_gen | `resource` | | | |
| code_example | `resource` | | | |

### 3.4 Center 执行顺序（`intent_extractor.py:46-52`）

`auto:1 < visualization:2 < resource:3 < exercise:4 < plan:5`（数值越小越先执行）

### 3.5 `[存疑]` 意图数量与清单

- `[事实]` `INTENT_REGISTRY` 实际含 **11 条** `IntentDef`：`exercise_gen, resource_gen, code_example, tutor_question, learning_path, solve_problem, flashcard_gen, visualize, knowledge_graph, diagnose, profile_building`（`intent_extractor.py:164-260`）。
- `[事实]` `INTENT_TYPES`（`Literal`，`:24-29`）声明 **12 个**，多出 `unknown`（无对应注册项，仅作兜底类型）。
- `[事实]` `INTENT_CENTER_MAP` 有 **12 键**（含 `unknown`）。
- `[存疑]` 你口头提「我们不是只有四五个意图吗」——**代码事实是 11 条注册项 / 12 个类型常量**。需你确认「四五个」指的是哪一层口径（可能指 §3.2 的 5 个 Center，或 §2 的 5 大类 LLM 提示词类别，见 `_build_extraction_prompt` `:263-288`）。

---

## 4. 全部路由规则明细（任务 0.1 第 4 点）

### 4.1 一级 `CapabilityGate`（`capability_gate.py`）

**决策流**（`:149-198`）：
1. `:156` `mode != "auto"` → 查 `_MODE_TO_KIND`（`:42-47`）→ 命中直接放行（confidence `1.0`，`_EXPLICIT_MODE_CONFIDENCE`）；未命中未知 mode → NORMAL_CHAT（confidence `0.5`）。
2. `:171` 空消息 → NORMAL_CHAT（`empty_message`）。
3. `:178` `_match_capability()` 正则逐条匹配（**顺序即优先级，先中先得**）。
4. `:179` 未命中任何能力规则 → NORMAL_CHAT（`no_capability_evidence`）。
5. `:187` **疑问覆盖**：命中能力规则但含 `_QUESTION_RE` 且**不含** `_IMPERATIVE_RE` → 回落 NORMAL_CHAT（`question_over_capability:{rule}`，confidence `0.6`）。
6. `:194` 否则放行该能力（`capability_evidence:{rule}`，confidence `0.75`，`_CAPABILITY_CONFIDENCE`）。

**置信度常量**（`:49-51`）：`_CAPABILITY_CONFIDENCE=0.75` / `_NORMAL_CONFIDENCE=0.5` / `_EXPLICIT_MODE_CONFIDENCE=1.0`

**正则片段**（`:55-65`）：
- `_QUESTION_RE` = `什么|为什么|怎么|如何|是什么|何为|吗|呢|\?|？|讲讲|讲解|解释|介绍一下|说说|区别`
- `_IMPERATIVE_RE` = `帮我|给我|请|麻烦|劳驾`
- `_NO_PAST` = `(?![了过])`（生成动词后禁「了/过」，排除陈述过去，如「做了5道题都错了」）
- `_FILL = [^。？！?!;；\n]{0,%d}`（产物前的连接填充，长度可变）

**能力规则表 `_CAPABILITY_RULES`**（`:68-143`，**按序匹配**）：

| 序 | rule | 能力 | 模式要点 | 行号 |
|---|---|---|---|---|
| 1 | `verb_count_exercise` | EXERCISE | `(出\|来\|做\|生成\|设计)` + `(\d+\|中文数字)\s*道` + 题类 | `:70-78` |
| 2 | `verb_set_exercise` | EXERCISE | `(出\|来\|做\|生成\|设计\|给我)` + `(一套\|一份\|几道\|些)` + `(题\|练习\|习题\|试卷\|卷子)` | `:79-86` |
| 3 | `verb_topic_exercise` | EXERCISE | **不要求数量词**；动词 + 题型产物；**负向断言** `(?<!这道)(?<!那道)(?<!该)` 排除「帮我做这道题」（解题≠出题） | `:94-103` |
| 4 | `draw_diagram` | VISUALIZATION | `(画\|绘制\|生成\|做)` + 图类产物（流程图/思维导图/脑图…） | `:105-114` |
| 5 | `knowledge_graph_request` | VISUALIZATION | `(生成\|构建\|画\|绘制\|展示\|查看\|打开\|看看\|看)` + `(知识图谱\|图谱)` | `:116-123` |
| 6 | `make_plan` | PLAN | `(制定\|规划\|安排\|生成\|设计\|做)` + `(学习计划\|计划\|学习路径\|路径\|路线\|日程)` | `:125-132` |
| 7 | `request_material` | RESOURCE | `(帮我\|给我\|请\|生成\|整理\|推荐\|提供)` + 资料类产物（资源/讲义/闪卡/PPT…） | `:134-142` |

### 4.2 二级 `RouterAgent`（`router_agent.py`）

**决策流**（`:57-117`）：
1. `:68` 空消息 → inquiry 追问（`empty_inquiry`，`is_clear=False`）。
2. `:84` `mode != "auto"` → `_manual_mode_plan()`（`:189-210`）：`MODE_TO_INTENT`（`:44-49`：plan→learning_path / resource→resource_gen / exercise→exercise_gen / visualization→visualize）→ 查 `INTENT_CENTER_MAP` → 单任务（confidence `1.0`）。
3. `:87` `_keyword_route()`（见下）。
4. `:88` 有命中 → `_sort_by_confidence()`（`:212-218`：按 `-confidence`，再按 `_CENTER_EXECUTION_ORDER`）→ `needs_confirmation = len>=3`（`_CONFIRM_THRESHOLD`）→ 返回（`strategy="keyword"`）。
5. `:105` 全无命中 → **fallback tutor**（`strategy="fallback_tutor"`，confidence `0.0`）。

**`_keyword_route` 打分细节**（`:119-187`）：
1. `:126-129` 遍历 `INTENT_REGISTRY`，`_score_intent` ≥ `_KEYWORD_FLOOR=0.3` 才入选。
2. `:134` 按分降序。
3. `:146` **问题检测 checkpoint**：存在「非 auto 意图」(`INTENT_CENTER_MAP != "auto"`) + 消息含 `_QMARKS`（`:142-143`） + 无 tutor≥0.4 → **强制注入 tutor_question（0.55）到队首**，防「画图+出题」等强工具词吸走答疑。
4. `:157` **互斥过滤** `_MUTEX_GROUPS`：组内多命中时按 `(分数, _INTENT_PRIORITY)` 保留最优。
5. `:168` **置信度过滤**：保留 ≥ `_CONFIDENCE_THRESHOLD=0.4`；若全不过则取最高分 1 个。
6. `:172-185` 每个入围意图 → 一个 `CenterTask`（含 `_mock_extract_params` 抽参）。

**阈值常量**（`:36-40`）：`_KEYWORD_FLOOR=0.3` / `_CONFIDENCE_THRESHOLD=0.4` / `_CONFIRM_THRESHOLD=3`

**`_score_intent`**（`intent_extractor.py:320-338`）：

```
exclusive_keywords 命中 → 0.0（一票否决）
hits = 关键词命中数
hits>=3 → base=0.9 ; hits>=2 → base=0.75 ; hits>=1 → base=0.5 ; else 0.0
score = base × intent_def.confidence
```

各意图 `confidence`：默认 `0.85`；`tutor_question=0.6`（`:197`，注释：单命中 0.5×0.6=0.30 被 0.3 门槛滤掉）；`profile_building=0.7`（`:258`）；`diagnose=0.8`（`:243`）。

**互斥组**（`intent_extractor.py:300-303`）：`{solve_problem, exercise_gen}`、`{visualize, resource_gen}`。
**优先级**（`:295-298`）：`visualize=10`、`solve_problem=5`。

### 4.3 编排层兜底（`chat_center.py:204-214`）

`[事实]` **gate 权威兜底**：一级判定的能力中心若未被二级结果命中（二级回落 tutor），则**用显式 mode 重建计划**（`mode=decision.kind.value.lower()`），保证一级判定不被二级关键词路由推翻。

### 4.4 `[存疑]` 待确认的记忆性说法

`[存疑]` 此前记忆中「`declared intent in [INQUIRY, DIAGNOSE, PROFILE]` 有特殊放行」——**逐行核查未发现该逻辑**。代码中与「疑问/兜底」相关的实际机制只有两处：① `_keyword_route:146` 的 tutor_question 注入 checkpoint；② NORMAL_CHAT 早返回时把能力信息塞入 `task.context["capability_route"]`。请以本报告为准。

---

## 5. 上下文使用核查（任务 0.1 第 5 点）— **核心结论**

> **结论：路由决策不读历史 / 不读画像 / 不读上下文；只读「消息正文 + mode」。历史与画像仅在下游 LLM 执行层被消费。**

| 层 | 函数 | 是否读历史/画像/上下文做路由 | 证据 |
|---|---|---|---|
| 一级 | `CapabilityGate.decide` | **否** | `capability_gate.py:149-155` 形参含 `student_profile`/`context`，**函数体从未引用**；仅用 `message` + `mode` |
| 二级 | `RouterAgent.route` | **否** | `router_agent.py:65-66` 仅 `student_profile/context or {}`，随后**只塞进 `CenterTask.context`**（`:75,110,181,203`），打分不引用 |
| 编排 | `ChatCenter.route` | **否**（仅观测） | `chat_center.py:124-140` `_audit_context` 只从 `context["messages"]` 数 `turn_count` 供审计日志，**不参与判定** |

**历史的实际消费点**（与路由无关，属执行层）：
- `chat_center.py:312` `messages = history + [current]` → 写入 `context["messages"]`。
- `[事实]` 契约测试 `ai-service/tests/test_multiturn_context_contract.py` 证明多轮历史被 **TutorAgent / ContextBuilder / SummaryMaintainer** 消费，**不在路由层**。

`[推测]` 这解释了「多轮上下文/指代消解/组合任务处理弱」的现象根因：路由阶段对历史无感知，指代（「那再来几道」）无法在路由决策中被解析。

---

## 6. 路由可独立调用性（任务 0.1 第 6 点）

| 组件 | 可独立调用？ | 有无 IO / LLM | 证据 |
|---|---|---|---|
| `CapabilityGate.decide` | ✅ **是，纯同步函数** | 无 | `capability_gate.py:147` 文档明示「纯函数，无 IO、无 LLM」；仅 `re` 匹配 |
| `RouterAgent.route` | ✅ **是（async）** | 无 LLM/网络 | `router_agent.py` 全程无 LLM 调用；`_mock_extract_params` 为纯文本处理 |
| `ChatCenter.route` | ✅ **是（async）** | 无 IO | 只调 gate + router + `_audit_context`（纯计数），**不含生成任务** |
| 生成执行 | ❌ 分离 | 有 LLM | `ChatCenter.execute` / `ChatTaskDispatcher.execute` 才是执行层，与 `route()` 解耦 |

**结论**：路由可**完全独立于生成任务**被调用与测试——这为后续「路由可独立评测 / 140 条测试集」提供了可行性前提。`[事实]` 契约测试 `test_capability_gate.py`、`test_routing_ownership_contract.py` 已在独立调用路由层。

**所有权契约**（`test_routing_ownership_contract.py`，AST 级强制）：
- `app.services.capability_gate` 的唯一引用方 = `chat_center.py`；
- `app.centers.router_agent` 的唯一引用方 = `chat_center.py`；
- **API 层禁止直接 import 路由符号**。

---

## 7. 版本 / 配置 / 工作区状态（任务 0.1 第 7 点）

**Git**：分支 `for-work`；HEAD `24dd24d`。

**⚠️ 基线必须同时锚定「提交 + 工作区」**（多处与路由相关文件存在**未提交改动**）：

| 文件 | 状态 | 与路由关系 |
|---|---|---|
| `ai-service/app/services/capability_gate.py` | **M（+17 行）** | **一级路由核心**：新增 `verb_topic_exercise` 规则（`:87-103`） |
| `ai-service/app/centers/chat_task_dispatcher.py` | M | 二级→执行分发 |
| `ai-service/tests/test_chat_task_dispatcher.py` | M | 路由相关测试 |
| `ai-service/app/agents/base_agent.py`、`exercise_agent.py`、`centers/exercise_center.py`、`prompts/tutor_agent/system.yaml`、`tests/test_project_path_a.py`、`start-all.sh`、前端若干文件 | M | 执行层/前端（非路由判定，但同处工作区） |
| `ai-service/tests/test_prompt_role_contract.py` 等 | ?? 新增 | 测试 |

> `[事实]` `router_agent.py`、`chat_center.py`、`intent_extractor.py`、`schemas.py` **本工作区无未提交改动**（干净）。
> **风险提示**：`capability_gate.py` 的 +17 行意味着**「现有路由行为」不是一个稳定快照**。后续测试基线须显式声明所锚定的 commit **与** 工作区状态，否则结论不可复现。

**相关配置 / 常量总表**：

| 项 | 值 | 位置 |
|---|---|---|
| 显式 mode 枚举 | `auto\|plan\|resource\|exercise\|visualization` | `app/api/models.py:103-113` (`UnifiedChatRequest.mode`) |
| 一级置信度 | 0.75 / 0.5 / 1.0 | `capability_gate.py:49-51` |
| 二级阈值 | floor 0.3 / conf 0.4 / confirm 3 | `router_agent.py:36-40` |
| 打分 base | 0.9 / 0.75 / 0.5 | `intent_extractor.py:330-335` |
| 互斥组 | 2 组 | `intent_extractor.py:300-303` |
| 审计白名单字段 | ts, trace_id, conversation_id, route, route_reason, context_turn_count, profile_fields_used, kb_chunks_used, model_latency_ms, retry_count, sse_terminal_event, error_code | `app/services/routing_audit.py` |

`[事实]` 审计字段 `profile_fields_used` / `kb_chunks_used` 当前恒为 `None`（未接线）。审计日志**已脱敏**、**字段白名单**，满足「可审计路由决策记录」要求。

---

## 8. 对「疑似问题」的初步核对（仅事实，不含改法）

| 疑似问题 | 核查结论 | 证据 |
|---|---|---|
| ① 规则膨胀逼近自然语言语义理解 | `[事实]` 一级 7 条正则 + 二级 11 意图关键词表，且 `verb_topic_exercise` 仍在扩 | `capability_gate.py:68-143`；工作区 +17 行 |
| ② 一级过早判 NORMAL_CHAT、阻断隐式产物识别 | `[事实]` **成立**：NORMAL_CHAT 在 `:170` 短路返回，二级完全不被调 | `chat_center.py:170-195` |
| ③ 多轮上下文 / 组合任务 / 指代消解弱 | `[事实]` **成立（路由层）**：路由不读历史/画像/上下文 | §5 |
| ④ 一二层职责边界不清 | `[事实]` 边界**有定义但存在交叉**：二级回落 tutor 时，一级用显式 mode 强行重建（gate 权威兜底） | `chat_center.py:204-214` |

---

## 9. 已知遗留项（`[事实]`，供后续阶段）

1. `RouterAgent.__init__(intent_extractor=...)` — 参数**保留但 `del` 掉未使用**（`router_agent.py:51-55`），为兼容 10 个既有测试签名，属 P3-B 登记项。
2. `_QMARKS`（`router_agent.py:142`）与 `INTENT_REGISTRY["tutor_question"].keywords` **语义相近但有意独立维护**（P3 决定：只登记不合并）。
3. `IntentExtractor.extract/extract_multi`（`intent_extractor.py:399+`）**未接入实时链路**（实时用 `_mock_extract_params`；LLM 路径用 `EXTRACTION_PROMPT`）。
4. `RouterAgent` 命名与位置不符（叫 Agent 却在 `centers/`、非 LLM Agent），改名排在 P3-B（`router_agent.py:14-16`）。

---

## 10. 未验证 / 待外部确认项

- `[未验证]` 前端 → Java → Python 的完整上游链路（本文只覆盖 Python 侧；Java 持久化与 SSE 回写未在本任务范围内逐行核查）。
- `[未验证]` 140 条测试集的判分口径（属 Task 0.2，未开始）。
- `[存疑]` 「意图只有四五个」的准确口径（见 §3.5）。
- `[存疑]` 记忆性说法「INQUIRY/DIAGNOSE/PROFILE 特殊放行」是否曾存在（现码无，见 §4.4）。
