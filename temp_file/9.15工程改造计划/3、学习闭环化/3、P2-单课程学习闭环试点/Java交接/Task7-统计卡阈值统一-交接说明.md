# Task 7 交付说明 — 统计卡阈值统一（Java 交接）

- **日期**：2026-09-28
- **阶段**：P2 单课程学习闭环试点 / Task 7
- **依据**：《P2-单课程学习闭环试点实施方案》§〇 问题 2（Java 统计卡阈值行）、§2.2 缺口③、§六 Task 7 行、§七 A2、§十 回滚、决策点 1 = 甲；《P1-学习状态与学习证据V1设计方案》§3.4 五分档
- **定性**：**交接任务**（Java 单 commit 改动）。本文件给出精确改动位置、目标值、口径裁决与核验方式；不含代码改动。
- **一句话**：把 Java 统计卡的分桶阈值从 `0.8f / 0.4f` 改成 `0.85f / 0.6f`，与 P1 §3.4 的 `mastered` / `proficient` 边界对齐，使前端统计卡与知识图谱、Python 侧读数同口径。

---

## 一、要改的位置（精确到行）

文件：`backend/src/main/java/com/university/learning/service/impl/NodeMasteryServiceImpl.java`
方法：`getDistribution(Long userId, String courseId)`

当前代码（`78`–`85`）：

```java
// mastery >= 0.8 → mastered, >= 0.4 → in_progress, < 0.4 → weak   ← :78 注释，改后需同步更新
for (NodeMastery nm : list) {
    float m = nm.getMastery() != null ? nm.getMastery() : 0;
    totalMastery += m;
    if (m >= 0.8f) mastered++;                                       // :82 → 0.85f
    else if (m >= 0.4f) inProgress++;                                // :83 → 0.6f
    else weak++;
}
```

目标代码：

```java
// mastery >= 0.85 → mastered, >= 0.6 → in_progress, < 0.6 → weak（与 P1 §3.4 对齐）
for (NodeMastery nm : list) {
    float m = nm.getMastery() != null ? nm.getMastery() : 0;
    totalMastery += m;
    if (m >= 0.85f) mastered++;
    else if (m >= 0.6f) inProgress++;
    else weak++;
}
```

**共三处**：`:82` 的 `0.8f` → `0.85f`、`:83` 的 `0.4f` → `0.6f`、以及 `:78` 的注释（留在原处即变成**错误的谎言**，必须同步改）。

**`overall_pct` 不受影响**（它是 `totalMastery / size`，与分桶无关），**不要顺手改**。

---

## 二、口径裁决（★ 存在文档内部矛盾，本文件据此裁决）

P2 内部有两处独立记载，均指向 `0.85f / 0.6f`：

| 出处 | 原文 |
|------|------|
| §〇 问题 2 表格 | `改 0.85f / 0.6f（与 P1 §3.4 对齐）` |
| §六 Task 7 行 | ``NodeMasteryServiceImpl.getDistribution` `0.8f/0.4f → 0.85f/0.6f`` |
| §2.2 缺口③ 表 | `0.8f / 0.4f` → `0.85f / 0.6f` |

但 **P1 §3.4 第 222 行**字面写的是另一种口径：

> `1. NodeMasteryServiceImpl.getDistribution 的 0.8f / 0.4f → 按上表重算分桶（mastered = >=0.85，proficient+learning 合并为 in_progress 的口径需同步登记）；`

若按「`proficient + learning` 合并」，in_progress 下界应为 `0.3`（learning 的下界），而非 `0.6`。

**裁决：采用 `0.85f / 0.6f`（即 in_progress = `[0.6, 0.85)`，weak = `[0, 0.6)`）。**

理由：
1. **P2 更晚、更具体，且已修正过 P1 的表述**——P2 §2.2 明确写了「**重要澄清（P1 §3.4 表述需修正）**」，说明 P2 是在逐条复核 P1 后写的修正版，其阈值结论优先。
2. P2 三处独立记载一致，无内部分歧。
3. 语义更可用：统计卡三桶对应「已掌握 / 达标 / 未达标」，`0.6` 是**达标线**（= `proficient` 下界），对「要不要补这个节点」有直接行动含义；若用 `0.3`，`in_progress` 会包含 `beginner`（"初步接触"），统计卡会把"刚摸过一点"也算进"学习中"，失去区分度。

> **需 Java 同学与队长知悉**：这与 P1 §3.4 line 222 的字面表述不一致。本文件按 P2 裁决执行；若队长改判为 `0.3f`，只改这一个数字即可，其余步骤不变。

**P1 §3.4 五分档（供核对，逐字照抄 P1 line 215-219）**：

| 掌握度 | `level` |
|--------|---------|
| `null` / `0.0` | `not_started` |
| `(0, 0.3)` | `beginner` |
| `[0.3, 0.6)` | `learning` |
| `[0.6, 0.85)` | `proficient` |
| `[0.85, 1.0]` | `mastered` |

边界是**左闭右开**：`0.85` 进 `mastered`，`0.6` 进 `proficient`（即 Java 的 `in_progress`）。Java 的 `>=` 判断与此一致。

---

## 三、验收（A2）

**门禁 A2**：`getDistribution` 分桶结果与 P1 §3.4 一致。

**路由入口**：`KnowledgeGraphController.java:50`

```
GET /api/knowledge-graph/masteries/{courseId}?userId=<id>
```

> **★ 不要改错文件**：本功能的落点是 `KnowledgeGraphController`（`@RequestMapping("/api/knowledge-graph")`，`GET /masteries/{courseId}`），**不是** `GraphController`（`@RequestMapping("/api/graph")`，`POST /masteries`）。后者是 Task 6 的落库点。两个类名字接近，P2 §2.4 专门做过澄清。

**可执行核验步骤**（需登录态）：

构造边界数据后调用该端点，核对 `data.distribution`：

| 节点 mastery | 期望分桶 |
|--------------|----------|
| `0.0` | `weak` |
| `0.3` | `weak`（0.3 < 0.6） |
| `0.59` | `weak` |
| `0.6` | `in_progress` |
| `0.84` | `in_progress` |
| `0.85` | `mastered` |
| `1.0` | `mastered` |

**边界必测**（`0.6` / `0.85` 是 `>=` 的临界点，改错符号会漏）：
- `mastery == 0.6` → `in_progress`，**不是** `weak`
- `mastery == 0.85` → `mastered`，**不是** `in_progress`
- `mastery == null` → 视作 `0` → `weak`（现有 `nm.getMastery() != null ? : 0` 已兜底）

---

## 四、必须避开的两个坑

### 1. 既有测试会挂（P2 §九 风险 4）

P2 §九风险 4 原文：`阈值改动影响既有 1651 测试`。

`getDistribution` 是既有方法，若 Java 侧已有针对 `0.8f / 0.4f` 的断言（尤其是构造 `mastery = 0.5` 期望 `in_progress`、或 `mastery = 0.7` 期望 `in_progress` 的用例），改阈值后会由绿转红。

**处理原则**：这些测试断言的是**旧口径**，属于「需要随口径一起更新的既有测试」，**不是**「改测试来迎合实现」。改测试时必须在 commit message 里写明「阈值口径由 0.8/0.4 统一为 0.85/0.6（P1 §3.4）」。**不得**为了少改测试而放弃统一（那会让缺口③永不闭合）。

**建议排查范围**：`mvn -Dtest='*NodeMastery*' test`，只看与 `getDistribution` / `distribution` / `mastered` / `in_progress` 相关的断言。

### 2. 历史数据的可视化跳变（P2 §九 风险 5，与本 Task 相邻）

P2 §九风险 5：`默认值 0.5→0.0 历史数据跳变`。该风险由 P2 Task 1 在 **Python 侧**处理（`plan_center._old_mastery` / `plan_service.py:390` 的兜底由 `0.5` 改 `0.0`），**不经 Java**。但改完 Task 7 的阈值后，**存量 `node_masteries` 行**会因新阈值重新分桶：一个 `mastery = 0.7` 的旧节点，改前算 `in_progress`（0.7 ≥ 0.4），改后仍算 `in_progress`（0.7 ≥ 0.6）；而一个 `mastery = 0.45` 的旧节点会从 `in_progress` 掉到 `weak`。

**这是预期行为，不是 bug**（口径统一的必然结果），但需在验收记录与给队长的报告里**显式登记**，避免被误判为数据损坏。**不迁移、不刷数据**。

---

## 五、回滚

- 回滚方式：revert Java 侧本次单 commit。
- 回滚后行为 == `0.8f / 0.4f` 旧口径，统计卡与图谱口径重新分裂（缺口③复现），系统仍可运行。
- **无数据副作用**——本 Task 只改判断阈值，不写任何行。回滚不需要任何数据操作。

---

## 六、明确不做

1. **不改 Python 侧任何阈值**：`graph_service._mastery_to_status/_color` 已是 `0.85/0.6/0.3/0`（P2 §2.2 复核确认「已是目标值，不动」）。
2. **不改 Python 技能分级**：那是 P2 另一个交付项（`exercise_profile_service.py:78` `acc >= 85` / `:80` `acc >= 60`，百分制 —— P2 §〇/§2.2 引作 `:77-82`，实测精确行为 78/80），由 Python 侧另行处理，与本 Task 无关。
3. **不改 `overall_pct` 的算法**。
4. **不迁移存量数据**（见 §四.2）。
5. **不代做 Java 改动**——本文件是交接清单。

---

## 七、交接确认清单（Java 同学勾选）

- [ ] `NodeMasteryServiceImpl.java:82` `0.8f` → `0.85f`
- [ ] `NodeMasteryServiceImpl.java:83` `0.4f` → `0.6f`
- [ ] `:78` 注释同步更新（否则成为错误的谎言）
- [ ] 已确认知悉 §一「`overall_pct` 不动」
- [ ] 已确认落点是 `KnowledgeGraphController` 而非 `GraphController`（§三）
- [ ] 已排查既有测试（§四.1），更新旧口径断言并在 commit message 注明口径统一
- [ ] A2 边界核验已执行（`0.6` → `in_progress`；`0.85` → `mastered`）
- [ ] 已确认 §二 的口径裁决（`0.6f` vs P1 line 222 的 `0.3f`），如改判已通知队长
