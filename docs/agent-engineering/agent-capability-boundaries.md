# Agent 能力与职责边界梳理（解耦设计·任务 B）

> **性质**：只读设计梳理，**不含**代码改动、重命名或重构实施。
> **依据**：`agent-routing-architecture-audit.md`（已验收）+ 本轮定向复核。
> **基准**：HEAD `24dd24d`。**日期**：2026-10-13　**产出人**：Coding Agent A
> **证据口径**：每条结论标注 `文件:行`。

---

## 一、五类概念的分层定义

| 层 | 含义 | 载体 |
|---|---|---|
| 用户意图 | 用户自然语言诉求的类型 | `INTENT_TYPES`（`intent_extractor.py:24-29`） |
| 可执行业务能力 | 一次可独立交付产物的动作 | Center 的 execute / 服务方法 |
| 业务工作流 | 多步 Agent 编排的流水线 | `app/workflows/*`、PlanCenter `_generate_base_plan` |
| Agent 实现 | 具体产出内容的 LLM/规则单元 | `app/agents/*` |
| 辅助服务 | 无产物、被复用的算法/工具 | `app/services/*` |

---

## 二、能力归属矩阵

### 2.1 注册意图覆盖的能力（11 项）

| 能力 | 注册意图 | 执行 Center / Agent | 可独立 | 依赖 | 输入 → 输出 | 副作用 | 重复实现 |
|---|---|---|---|---|---|---|---|
| 概念答疑 | `tutor_question` | AutoCenter `_run_tutor` → **TutorAgent** | ✅ | 无 | question+messages → response(+domain) | 画像后台提取 | TutorCenter 同构实现 |
| 逐步解题 | `solve_problem` | AutoCenter `_run_solve` → **SolveAgent** | ✅ | 无 | question → steps/solution/confidence | 无 | ExerciseCenter `solve_stream` |
| 学习诊断 | `diagnose` | AutoCenter `_run_diagnose` → **DiagnoseAgent**（**规则+BKT**） | ⚠️ | 无 attempts 时**直调 ExerciseAgent 出题** | topic/skills → mastery_vector/report | 无（纯内存） | — |
| 画像构建 | `profile_building` | AutoCenter `_run_profile_building` → **ProfileAgent** | ✅ | 无 | message+profile → profile_delta | **画像更新**（返回 Java） | 完整度校验与 ProfileWorkflow 重复 |
| 出练习题 | `exercise_gen` | ExerciseCenter → **ExerciseAgent** | ✅ | 无 | topic/count/difficulty → questions | 无 | — |
| 生成资源 | `resource_gen` | ResourceCenter → **ResourceGenWorkflow**（Director 选 Content/Code/MindMap/Project/InteractiveDiagram） | ✅ | **InquiryService 前置澄清** | topic+type → content_blocks | 无 | — |
| 代码示例 | `code_example` | ResourceCenter → Workflow → **CodeAgent** | ✅ | 同上 | topic+language → code blocks | 无 | — |
| 闪卡 | `flashcard_gen` | ❌ **未接线**（FlashcardAgent 休眠） | ❌ | — | — | — | — |
| 可视化 | `visualize` | VisualizationCenter → **TutorAgent 前置 + VisualizePipeline** | ✅ | 依赖 tutor 先产生文本 | question+answer → blocks | 无 | AutoCenter `_maybe_visualize` 旁路 |
| 知识图谱 | `knowledge_graph` | VisualizationCenter → GraphService | ✅ | masteries | course_id → graph | 无 | GraphCenter 独立端点 |
| 学习规划 | `learning_path` | PlanCenter `_generate_base_plan` → **Goal→Decompose→Schedule** | ✅ | 无 | topic+profile → milestones/steps | 无 | CreatePlanFromPath 复用同函数 |

> `flashcard_gen` 是**注册但无实现**的意图——注册表与真实能力**不一致**。

### 2.2 未注册但真实存在的能力

| 能力 | 执行者 | 说明 |
|---|---|---|
| 计划调整 | PlanCenter `_run_adjustment` → AdjustmentAgent | intent=`adjust_plan`，非注册意图 |
| 今日任务/计划状态/复习日程 | PlanCenter 端点方法 | 只读计算，Java 传入 steps |
| 完成步骤巩固 / 回归检测 | PlanCenter → **跨域直调 ExerciseCenter** | `_exercise_center()` 惰性构造 |
| 批改 / 错因分析 / 练习分类 / 会话分析 / 仪表盘 / 画像富化 | **ExerciseCenter 服务集合** | 9 个端点方法，非路由能力 |
| 自动可视化旁路 | AutoCenter `_maybe_visualize` | 预筛 + VisualizePipeline，不产出独立任务 |
| 资源问答澄清 | InquiryService | 独立 LLM 澄清路径 |

---

## 三、最主要的职责冲突（优先 5 项）

| # | 冲突 | 代码证据 | 影响范围 | 可能调整方向 |
|---|---|---|---|---|
| 1 | **意图决策与执行计划混杂** | `chat_center.py:170-214`：Gate 早退、RouterAgent、gate 权威回落三处生成 ExecutionPlan | 复合/边界输入的路由正确性（"讲解+出题"塌缩） | 决策与计划生产收敛到**单一规划器** |
| 2 | **能力映射表重复维护** | `_KIND_TO_CENTER`(`chat_center.py:46-51`)、`_center_for`(`chat_task_dispatcher.py:329-340`)、`INTENT_CENTER_MAP`/`_CENTER_EXECUTION_ORDER`(`intent_extractor.py:31-52`)、`MODE_TO_INTENT`(`router_agent.py:44-49`)、`_MODE_TO_KIND`(`capability_gate.py:42-47`) | 新增域需改 ≥5 处 | 建**单一能力注册表** |
| 3 | **AutoCenter 与 Dispatcher 重复调度** | AutoCenter 按 intent 再分派(`auto_center.py`)；Dispatcher 已按 mode 分派(`chat_task_dispatcher.py:329-340`） | 两层分派职责重叠、难判定谁决定执行者 | AutoCenter **降级为 auto 域执行体**，取消其"二次路由"语义 |
| 4 | **Center 间直接调用** | `plan_center.py:623-627` 直调 ExerciseCenter；`visualization_center.py:44-59` 内嵌 TutorAgent | 域边界消失、循环依赖风险 | 跨域改**显式接口/依赖注入** |
| 5 | **上下文/SSE/产物处理归属不清** | 上下文三处自建（`chat_center.py:312-319`、AutoCenter `_run_solve`、TutorAgent）；SSE 组装在 Dispatcher；产物合成在 `_summarize_product` | 契约漂移、呈现与调度耦合 | ContextBuilder 归 Agent 层；SSE 归 events 层；产物合成归 Center |

> 另：`DiagnoseAgent` 直调 `ExerciseAgent`（`diagnose_agent.py:4,63`）——**唯一 Agent→Agent 直调**，本质是"诊断能力依赖出题能力"，应由 Center 组装而非 Agent 内互调。

---

## 四、建议的职责边界

| 组件 | 应承担 | 不应承担 |
|---|---|---|
| CapabilityGate | 一级能力判定（是否需专用产物） | 选 Center/Agent |
| RouterAgent | 二级意图→任务、排序、互斥 | 业务内容、SSE |
| ExecutionPlan | **唯一**任务/顺序/映射真源 | — |
| ChatTaskDispatcher | 顺序调度 + 事件泵 | 正文合成、业务判断 |
| AutoCenter | auto 域执行（tutor/solve/diagnose/profile） | 二次路由（并入 Dispatcher） |
| 业务 Center | 业务编排 + 产物合成 | 其他域直接调用 |
| Agent | 单一职责产出 | 路由、跨 Agent 直调 |
| ContextBuilder | 上下文装配（唯一点） | 各层自建 |

**内部实现 Agent（不应暴露给路由）**：GoalAgent、DecomposeAgent、ScheduleAgent（PlanCenter 内部）、AnalysisAgent/CodeGeneratorAgent/ReviewAgent（VisualizePipeline 内部）、DiagnoseAgent 内嵌的 ExerciseAgent。**休眠 6 个**（Flashcard/Reading/Reflection/Image/ExerciseVariant/LayeredExplain）应先决策去留再接线。

---

## 五、最小解耦顺序（4 小阶段）

> 原则：保留现有 Center/Agent；先契约后结构；不新增中间层；不破坏 Java 持久化与现有 SSE；每阶段可独立验证、独立回滚。

| 阶段 | 目标 | 改动范围 | 验证 | 回滚 |
|---|---|---|---|---|
| **S1 能力注册表收口** | 单一真源：intent↔kind↔center↔order | `intent_extractor`/`capability_gate`/`router_agent`/`chat_center` 只引用，不各建表 | 现有关键词路由单测全绿 | 保留旧表只读镜像 |
| **S2 意图决策与计划分离** | 决策只判能力，计划只产任务 | ChatCenter.route 拆分两职责 | 场景 A–E 路由快照一致 | 一次性切回 route |
| **S3 AutoCenter 定位归位** | 取消二次路由歧义 | AutoCenter 语义收窄为 auto 域执行 | auto 域全链路用例 | 保留原 execute |
| **S4 上下文与跨域契约** | ContextBuilder 唯一装配；跨域改接口 | `chat_center.py:312`、AutoCenter `_run_solve`、`plan_center.py:623-627`、`visualization_center.py:44` | 上下文一致性 + 跨域用例 | 各自保留原路径 |

---

## 六、需架构师裁决的问题

1. `flashcard_gen` 意图保留（接线 FlashcardAgent）还是从注册表删除？
2. 休眠 6 个 Agent：接线还是废弃？
3. AutoCenter 是**降级为执行体**还是**并入 Dispatcher**？
4. 多任务是否需要链式传参（上游结果喂下游）？现状为顺序拼接。
5. 能力注册表的**粒度与归属**：放 services 还是新建顶层模块？
6. `code_example` 与 `resource_gen` 同映射 resource：是否需独立能力标识？
7. 复合意图判定：一级 Gate 的疑问句式压制是否放宽？
