# 目标路由架构设计（Task C·目标架构｜C.1 收口修订）

> **性质**：只读目标架构设计，**不含**代码改动、重命名或重构实施。本轮为 C.1 设计收口，仅修订本文件。
> **依据**：`agent-routing-architecture-audit.md`（已验收）+ `agent-capability-boundaries.md`（已验收）+ 本轮定向核实。
> **基准**：HEAD `24dd24d`。**日期**：2026-10-13　**产出人**：Coding Agent A
> **约束**：优先复用现有 Center/Agent，**不为命名好看新增类**；不改业务代码 / 路由规则 / SSE 协议。
> **C.1 修订要点**：解耦「意图 / 能力 / 动作 / 产物」四层；RouteDecision 支持多候选与关系、区分规则分与校准置信度；ExecutionPlan 分离执行顺序与数据依赖；AutoCenter 仅禁全局重判；新增「执行前裁决」消费 `needs_confirmation`；迁移序以映射一致性测试先行、结构重构非零风险。

---

## 一、四个逻辑职责的边界

| 职责 | 一句话定义 | 输入 → 输出 | 不做 |
|---|---|---|---|
| **IntentDecision** | 识别用户意图，**产出候选集** | message(+mode/profile/context) → `RouteDecision`（多候选 + 关系） | 不选执行者、不判依赖、不排序、不执行 |
| **CapabilityRegistry** | 定义「意图 / 能力 / 动作 / 产物」四层及其映射 | — → 规范化映射表（静态真源） | 不含运行时状态、不执行 |
| **PlanBuilder** | 生成合法 `ExecutionPlan`，并**执行前裁决**（追问/确认/放行） | `RouteDecision` → `ExecutionPlan`（或追问/确认结论） | 不重判意图、不执行 |
| **Dispatcher** | 依计划执行 | `ExecutionPlan` → SSE 事件流 | **不重新判断用户意图**、不改计划 |

> 关键分离：**意图 ≠ 能力 ≠ 动作 ≠ 产物**，且 **执行顺序 ≠ 数据依赖**。现状把前四者揉进 `ChatCenter.route`（`chat_center.py:142-221`），是首要解耦点。

---

## 二、CapabilityRegistry：四层分离与映射（C.1 核心修订）

**不能假定一个 intent 必然对应一个能力。** 须区分四层：

| 层 | 定义 | 示例 |
|---|---|---|
| **意图 Intent** | 用户想达成什么（语言层，可多义） | 「讲解进程调度」/「出5道题」/「做成闪卡」 |
| **业务能力 Capability** | 系统稳定提供的能力（≈ Center 语义） | 答疑作答 / 题目生成 / 计划生成 / 资源生成 / 可视化 |
| **执行动作 Action** | 能力内具体操作（≈ Center 内分支） | 资源域：`generation`；计划域：`new_plan` / `adjust_plan` |
| **产物类型 Artifact** | 动作最终产出的对象类型 | `flashcard` / `mindmap` / `quiz` / `summary` |

**映射关系（非 1:1）**：
- `intent → capability`：**1:N 或 N:1**。例：`tutor_question` → 答疑能力；`flashcard_gen` → 资源生成能力（与 `resource_gen` **竞争同一能力**，只是期望产物不同）。
- `capability → action`：1:N。资源生成能力含 `generation` 等动作。
- `action → artifact`：1:N，由 `params` 决定（如 `resource_type`）。**产物类型是运行时参数的结果，不是意图的固有属性**。

**规范化真源表（替代散落的 intent→center 映射）**：
```
CapabilityMapping  # 静态，一行一条「意图候选」
├─ intent: str
├─ capability: str             # 业务能力 id（≠ CapabilityKind 枚举，见 §三）
├─ action: str|None            # 期望动作，可空（由运行时决定）
├─ expected_artifact: str|None # 期望产物类型，可空
├─ center: str                 # 执行 Center（auto/plan/resource/exercise/visualization）
├─ order: int                  # 编排序（现值 _CENTER_EXECUTION_ORDER）
├─ on_token: bool              # 逐字流（现值 _ON_TOKEN_MODES）
└─ registered: bool            # 是否已在 INTENT_REGISTRY 注册
```
> 现有 `INTENT_CENTER_MAP` / `_CENTER_EXECUTION_ORDER` / `_KIND_TO_CENTER` / `_center_for` / `MODE_TO_INTENT` / `_MODE_TO_KIND` 收敛为对**此表**的只读引用。`center` 列即兼容现有 Center 的锚点，不改变执行体。

---

## 三、RouteDecision：多候选 + 上下文 + 关系（C.1 修订）

现状 `RouteDecision` 隐含「一次判定一个 intent，且必属五种 `CapabilityKind`」。修订为：

```
RouteCandidate            # 一个候选意图
├─ intent: str
├─ capability: str|None   # 业务能力 id（字符串，非强枚举）
├─ rule_score: float      # 人工规则原始分（确定性、可复现）
├─ calibrated_confidence: float|None  # 校准后置信度；无校准器时 = None
├─ evidence: str          # 命中依据（正则组名/关键词），仅审计
└─ params: dict           # 抽参结果（topic/count/question…）

RouteDecision
├─ candidates: list[RouteCandidate]   # 多候选（≥1），按 rule_score 排序
├─ message_context: dict              # 会话/澄清上下文、已抽实体、mode/profile
├─ relations: list[IntentRelation]    # 意图间关系，见下
├─ is_clear: bool
└─ inquiry: str|None                  # 需追问时的问题文本
```

**IntentRelation（意图关系）** —— 复合与多轮的关键：
```
IntentRelation
├─ type: str            # composite_with | follow_up_of | refine_of | contrast_with
├─ from_idx: int        # candidates 下标
└─ to_idx: int|None     # 关联候选；跨轮时为 None（由 message_context 承载）
```
- 「先讲解…再出题」→ 两候选 + `composite_with`。
- 「再出5道题」（承接上一轮讲解）→ `follow_up_of`，`to_idx=None`，前轮意图存 `message_context`。

**规则分 vs 校准置信度（必须区分）**：
- `rule_score`：**人工规则的确定性打分**。现状 `score = base × IntentDef.confidence`（`intent_extractor.py:320-338`，`IntentDef.confidence` 默认 0.85）与 `_CONFIDENCE_THRESHOLD = 0.4` 比较，本质是**规则分值**，**不是概率**——单词命中 0.5×0.85=0.425 只是「过规则阈值」，不代表 42.5% 概率正确。
- `calibrated_confidence`：需离线数据校准（如分数→命中率的映射曲线）。**当前无校准器 → 置 None**，不得把 rule_score 冒充为 confidence。阈值过滤继续用 rule_score，语义明确为「规则门槛」。

**不强制归入五种 CapabilityKind**：意图可用字符串能力 id 标识；`CapabilityKind` 降级为**执行体的分组标签**（用于 Center 编排），而非意图分类的强制枚举。

---

## 四、ExecutionPlan：任务 / 顺序 / 依赖三分（C.1 修订）

现状「顺序执行」被隐含当作「结果传递」。修订为**三字段分离**：

```
ExecutionPlan
├─ tasks: list[CenterTask]        # 任务集合（无序语义），已有
├─ execution_order: list[int]     # 编排顺序（默认按 mapping.order；用户显式指定则覆盖）
├─ user_specified_order: bool     # 顺序来自用户显式表达还是系统编排
├─ data_dependencies: list[[i,j]] # 真正数据依赖：任务 j 需任务 i 的产物作为输入
├─ is_clear / inquiry_question / needs_confirmation   # 已有
└─ route_meta: dict               # 审计（gate 判定 / 回落原因 / trace / relations）
```

**核心判据**：
- **`execution_order` ≠ `data_dependencies`**。顺序执行不自动传递结果。现状 Dispatcher 为固定上下文顺序执行（`chat_task_dispatcher.py:189-263`）——那只是 `execution_order`，**`data_dependencies` 恒空**。
- 仅当**下游显式需要上游产物**时才写入 `data_dependencies`。「先讲解，再出5道题」默认**无**依赖（出题不必须用讲解产物）；「基于刚才的讲解出5道题」才 `data_dependencies=[[0,1]]`。

**复合任务示例**「先讲解进程调度，再出5道题」：
```
RouteDecision.candidates = [
  {intent:"tutor_question", capability:"qa",       rule_score:0.55, calib:None, params:{question:…}},
  {intent:"exercise_gen",   capability:"exercise", rule_score:0.75, calib:None, params:{topic:"进程调度",count:5}},
]
relations = [{type:"composite_with", from_idx:0, to_idx:1}]
→ PlanBuilder：user_specified_order=true（"先…再…"），execution_order=[0,1] 按 order 排序
  data_dependencies=[]（默认不传递）→ ExecutionPlan{is_clear:true}
→ Dispatcher：按 execution_order 顺序执行；仅存在 data_dependencies 时才注入上游产物
```
> 现状该句**塌缩为单答疑**（`capability_gate.py:187-192` 疑问句式压制，场景 E 已验证）；任务间亦无依赖（`chat_task_dispatcher.py:189-263`）。`execution_order` + `data_dependencies` 即二者承载契约。

---

## 五、执行前裁决：追问 / 确认 / 放行（C.1 新增）

`needs_confirmation` / `is_clear` 现状**仅置位、无消费者**。须指定唯一裁决环节：

- **归属**：PlanBuilder 的末端子职责 **ExecutionGate（执行前裁决）**，输出三态：
  - **追问 inquiry** → `is_clear=false`，产 `inquiry` 事件（含追问文本），**阻断执行**。
  - **确认 confirm** → `needs_confirmation=true`，产确认事件，**阻断执行**等待用户。
  - **放行 pass** → 交 Dispatcher 执行。
- **现状错位**：澄清发生在 **Center 内**（`resource_center.py:37-38` InquiryService.check），即**派发之后**才追问，属「迟到裁决」。目标态把该决策**上提至 PlanBuilder**，Dispatcher 不再自行追问。
- **消费者明确**：Dispatcher 只读 PlanBuilder 的裁决结论；Java 侧只透传 `inquiry`/`confirm` SSE 帧。

---

## 六、AutoCenter：仅禁全局重判（C.1 修订）

- **保留** AutoCenter 现有**内部 Agent 分派**职责（auto 域内选 Agent/工具），**不并入 Dispatcher**。
- **仅禁止**其再次做**全局意图识别**（现状 `_run_solve` 二次按 intent 分派，语义上与上游 IntentDecision 重复）。
- 判据：域内 Agent 选择 = 执行细节（允许）；重新判定「用户到底要什么全局意图」= 越权（禁止）。

---

## 七、验证与迁移顺序（C.1 修订：结构重构非零风险）

**原则**：① 先冻结旧行为与 SSE 契约的**映射一致性基线**；② 再逐步迁移注册表；③ 最后迁移计划构建。**结构重构仍可能改行为，必须由基线快照守护**（纠正此前「纯结构、零行为风险」的表述）。

| 阶段 | 类型 | 目标 | 改动范围 | 验证 |
|---|---|---|---|---|
| **T0 映射一致性基线** | 无生产改动 | 固化 旧→新 映射快照 | 仅测试：Registry 表快照、路由结果快照、SSE 帧快照 | 快照入库，作为后续所有阶段的护栏 |
| **T1 注册表收口** | 结构重构 | CapabilityRegistry 单一真源 | 合并散落 6 表为 §二规范表；余者只读引用 | T0 快照全绿（路由结果字节不变） |
| **T2 决策/计划分离 + 执行前裁决** | 结构重构 | RoadDecision 多候选取代单判定；ExecutionGate 上提 | IntentDecision 只产 `RouteDecision`；PlanBuilder 独产 `ExecutionPlan` 并裁决 | T0 路由快照一致；追问/确认路径有独立用例 |
| **T3 AutoCenter 收编** | 结构重构 | 取消全局重判（保留域内分派） | AutoCenter 内部 Agent 分派不动，去掉全局 intent 二次判定 | auto 域全链路用例 |
| **T4 复合任务 + 数据依赖** | **行为优化** | 消解塌缩、接通 `execution_order`/`data_dependencies` | 放宽 Gate 疑问压制；Dispatcher 仅按 `data_dependencies` 注入产物 | 场景 E 由「单答疑」→「答疑+出题」；需 Gold 基线全量回归 |
| **T5 上下文/SSE/跨域收口** | 结构重构 | ContextBuilder 唯一装配；SSE 归 events；跨域改接口 | `chat_center.py:312`、AutoCenter `_run_solve`、`plan_center.py:623-627`、`visualization_center.py:44` | 上下文一致性 + 跨域用例；SSE 帧同 T0 快照 |

> **顺序原则**：**T0（基线）→T1（真源）→T2（决策/计划/裁决）** 在前，均以 T0 快照守护；**T4 行为优化**（唯一改反应阶段，需 Gold 基线全量回归）在后；**T5** 最后。T1/T2/T3/T5 目标为 SSE 帧与路由结果不变，但**视为非零风险**，逐阶段对基线核对。

---

## 八、flashcard_gen / adjust_plan 核实（保留，标注验证状态）

| 能力 | 路由可达 | 执行可达 | 产物可用 | 状态 |
|---|---|---|---|---|
| `flashcard_gen` | ✅ | ✅ | ⚠️ **不可靠** | 部分待 e2e |
| `adjust_plan` | ❌ | ✅ | ❌ | 部分待跨服务核实 |

### 8.1 `flashcard_gen`（已验证事实）
- **路由可达** ✅：`INTENT_REGISTRY[flashcard_gen]` 关键词 `闪卡|记忆卡|卡片|背诵|背一下`（`intent_extractor.py:214-220`）；单词命中 rule_score = 0.5×0.85 = **0.425 ≥ 0.4 阈值** → 保留独立意图 → 映射 `resource`（`intent_extractor.py:41`）。
- **执行可达** ✅：`ResourceCenter.execute` 真被调用（`resource_center.py:29`）。
- **产物缺口** ✅：`_mock_extract_params("flashcard_gen", …)` 只返 `{topic,count}`（`intent_extractor.py:379-383`），**无 `suggested_types`**；`ResourceCenter` 读 `suggested_types` → `primary_type=""`（`resource_center.py:56-57`）→ 传 `resource_type=""`（`resource_center.py:109`）→ Director `type_direct` 分支跳过（`resource_selector.py:164`），回落 `_rule_route(topic)`。
- **待端到端验证** ❓：针对**真实输入**，澄清后 topic 文本能否在 `_rule_route`（`resource_selector.py:80-83`）**实际命中闪卡关键词并产出 flashcard 产物**。链路上**无环节保证 `resource_type="flashcard"`**，需 e2e 实测确认产率。
- **结论**：`FlashCardAgent` 已装配（`resource_gen.py:121,138`），但**注册态 → 产物态不闭环**；`expected_artifact` 字段即此缺口的显式化。

### 8.2 `adjust_plan`
- **路由层** ❌：非 `INTENT_TYPES`（`intent_extractor.py:24-29`），不在 `INTENT_REGISTRY` → 一级 Gate 永不产出、二级关键词永不命中。
- **执行层** ✅：`PlanCenter.execute` 消费 `task.intent=="adjust_plan"`（`plan_center.py:48-49`）→ `_run_adjustment`（`plan_center.py:777-808`）。
- **生产构造点** ✅：Python 仓内仅 `plan_center.py:48` 一处生产字面量（tests 除外 `test_p1_agents.py:467`）——**无生产代码构造该 intent**。
- **待跨服务核实** ❓：**仅核实了 Python 仓**；Java 侧是否可能直接下发 `intent=adjust_plan` 未经核实。若 Java 可下发，则此为「外部触发、内部可达」路径，裁决结论不同。
- **结论**：**执行可达但 Python 侧路由不可达**；须架构师裁决接线、废弃，或确认由 Java 侧驱动（见 §九）。

---

## 九、待架构师裁决事项（收口，≤3 项）

1. **`flashcard_gen` 闭环方式**：补 `suggested_types` 使 `expected_artifact="flashcard"` 闭环（行为优化，归 T4），还是收为 `resource_gen` 的一个 `resource_type`（去注册，交由 Director 决定）？
2. **`adjust_plan` 去留**：注册为正式意图（接线 AdjustmentAgent）／从 `PlanCenter` 删除死路径／**确认由 Java 侧下发**（需先核实 Java 契约）？
3. **`data_dependencies` 语义**：上游产物注入下游用「文本拼接」还是「结构化字段」？是否需链式（多级）依赖？

> 其余项（Registry 归属、`on_token` 归属、疑问压制放宽粒度）归入 T1/T2/T4 实施细节，不作本轮裁决。
