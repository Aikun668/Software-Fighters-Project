# Stage 0.3 交接报告（Gold Labels 草案与审核准备）

> **阶段**：Stage 0.3 · Gold Labels 标注与审核准备
> **产出人**：Coding Agent A（Python AI 服务）
> **日期**：2026-10-13
> **状态**：✅ 完成，按约束**停止**（未运行旧路由基准评测、未修改 140 案与路由源、未进入 Stage 0.4）
> **基线**：commit `24dd24d`；9 个路由核心文件 SHA-256 与 Stage 0.2 基线**逐一复核一致**（未被本轮触碰）。

---

## 一、交付物（全在 `docs/agent-engineering/routing-baseline/`）

| 交付物 | 说明 |
|---|---|
| `routing_gold_review.csv` | 140 行 Gold 草案（14 列，UTF-8-BOM，`reviewer_decision` 全空待裁决） |
| `build_routing_gold.py` | 生成器（**不导入/不运行**任何 ai-service 路由代码，标准答案按「用户真实语义」判定） |
| `stage0.3_handoff.md` | 本报告 |

---

## 二、样本数量与检查结果（全部 ✅）

| 检查项 | 结果 |
|---|---|
| 行数 | **140**（与 `routing_cases.jsonl` 一一对应） |
| 列数 | **14** |
| `reviewer_decision` 非空数 | **0**（未自确认任何一条） |
| `gold_status` 分布 | **DRAFT_CONFIRMED=82 · POLICY_UNDECIDED=58** |
| 三拆分列一致性 | **0 处不一致**：`registered_intent/layer1_entry/independent_task` 仅当命中四特殊意图时填充，否则为 `—` |
| `gold_ask_clarify=是` | 33 条 |
| 复合任务（`gold_task_order` 含 `>`） | 24 条 |
| 路由源未改 | 9 文件 SHA-256 与基线**逐一相同** |

---

## 三、四意图三拆分（**未**归类为「产品能力缺失」）

对 `solve_problem / code_example / diagnose / profile_building`，逐案拆为三列，交由你裁决：

| 意图 | 覆盖案数 | registered_intent | layer1_entry | independent_task |
|---|---|---|---|---|
| solve_problem | 11 | 是 | 缺失 | **待裁决** |
| code_example | 3 | 是 | 缺失 | **待裁决** |
| diagnose | 9 | 是 | 缺失 | **待裁决** |
| profile_building | 8 | 是 | 缺失 | **待裁决** |

> 即：**「已注册」与「一级入口缺失」是事实**；「是否应作为独立执行任务」**是产品裁决项**，本轮**不代为判定**。

---

## 四、指定 4 案复核结论（C023 / C025 / C098 / C111）

| Case | 消息 | 上下文 | 结论 |
|---|---|---|---|
| C023 | 这道选择题答案是B吗，我不太确定 | 无历史 | **待澄清**（未给题面，参数不足）；意图处答疑/解题边界 |
| C025 | 这道题的第二问卡住了，帮我看看思路 | 无历史 | **solve_problem 待裁决** + **需追问补全题面** |
| C098 | 能不能画得更详细一点 | 有历史（TCP 流程图，topic=TCP三次握手） | **VISUALIZATION**，上下文充足，`DRAFT_CONFIRMED` |
| C111 | 对，我就是想转行 | 有历史（问学习背景，topic=用户画像） | **profile_building 待裁决**，上下文充足但一级无入口 |

---

## 五、需你决定的事项

1. **四意图独立任务裁决**（§三）：solve_problem / code_example / diagnose / profile_building 是否各作一等独立能力？若否，其触发可否依附现有中心？
2. **58 条 POLICY_UNDECIDED 逐条定调**（完整 ID 见 CSV `gold_status` 列）：
   - 解题类：C016–C025
   - 代码示例：C047、C103
   - 诊断/画像：C071–C080、C092、C107、C111
   - 隐式/澄清：C081–C087、C089、C090、C093、C095、C135
   - 复合任务编排（多中心是否顺序执行）：C116–C130
   - 否定表达：C133
   - 空/模糊输入默认行为：C136–C140
3. **澄清策略**：33 条 `ask_clarify=是` 的默认动作清单（澄清 / 默认答疑 / 静默画像）。

---

## 六、约束遵守声明

- ✅ **未运行**旧路由基准评测；生成器**不导入**任何路由代码，标准答案独立于旧预测。
- ✅ **未修改** 140 案、路由源、CapabilityGate / RouterAgent（9 文件哈希复核一致）。
- ✅ **未提交 / 未暂存 / 未还原 / 未覆盖**任何已有改动。
- ✅ **未自确认**任何 Gold Label（`reviewer_decision` 全空）；争议项一律 `POLICY_UNDECIDED`。
- ✅ 未进入 Stage 0.4 / 离线基准测试。

---

## 七、下一步（等待指令，不自行开始）

1. 人工审核 `routing_gold_review.csv`，填 `reviewer_decision`，裁决 §五三事项。
2. 经明确批准后，方进入 Stage 0.4（旧路由基准评测）。
