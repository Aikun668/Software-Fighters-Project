# Task 6 交付说明 — 掌握度落库接线（Java 交接）

- **日期**：2026-09-28
- **阶段**：P2 单课程学习闭环试点 / Task 6
- **依据**：《P2-单课程学习闭环试点实施方案》§〇 问题 2（掌握度落库行）、§二 缺口①、§六 Task 6 行、§七 A7、§八 退出条件 2、§十 回滚、决策点 1 = 甲
- **定性**：**交接任务，非本仓 Python 侧改动的替代品**。P1 已裁「落库责任在 Java」，Python 只算不落库；本文件是给 Java 同学的可核验清单，不包含任何代码改动。
- **前置**：P2 Task 1–5 已落地（commit `954db08`/`0901d59`/`48d4574`/`b98ff0a`/`767cf34`），Python 侧已产出 `mastery_updates` / `masteries` 结果，但**无人消费**。

---

## 一、要解决的问题

缺口①：两条拿到 Python 掌握度结果的链路，都在 `return Result.ok(result)` 处直接返回，**没有调用唯一落库入口**，导致 `node_masteries` 表无写入、掌握度永远不沉淀。

| 链路 | 代码位置 | 当前结尾 | 是否落库 |
|------|----------|----------|----------|
| Java `POST /api/plans/{planId}/progress` | `LearningPlanController.java:293-314` | `:310 return Result.ok(result);` | ❌ |
| Java `POST /api/graph/masteries` | `GraphController.java:62-72` | `:68 return Result.ok(result);` | ❌ |

**唯一落库入口**：`NodeMasteryController.upsert` → `NodeMasteryServiceImpl.upsert`（`@Transactional(rollbackFor = Exception.class)`）。此前**零自动调用方**。

---

## 二、Java 侧要改的两个点（精确到行）

### 2.1 注入 —— **不需要新增字段，两个 Controller 已经注入了**

```java
// GraphController.java:28-29
private final PythonClient pythonClient;
private final INodeMasteryService masteryService;      // ← 已存在

// LearningPlanController.java:26-30
private final ILearningPlanService planService;
private final IPlanStepService stepService;
private final PythonClient pythonClient;
private final INodeMasteryService masteryService;      // ← 已存在
```

**★ 不要加第二个 `INodeMasteryService` 字段**（如 §二.2/§二.3 示例里的 `nodeMasteryService`）。@RequiredArgsConstructor 会生成两个同类型构造参数，Spring 无法按类型消歧（需靠字段名回退匹配，脆弱且易报错），且纯属冗余。下列代码示例中的 `nodeMasteryService` 一律指**这个已存在的 `masteryService` 字段**，落地时请直接用它。

接口签名（已存在，无需新增方法）：

```java
// backend/src/main/java/com/university/learning/service/INodeMasteryService.java:21
NodeMastery upsert(Long userId, String nodeId, String courseId, Float mastery, Integer reviewCount);
```

注意：**没有批量 upsert**，多节点必须 Java 侧循环。

### 2.2 落点一 — `LearningPlanController.updateProgress`

在 `:306-309` 取到 `result` 之后、`:310 return` 之前插入落库。改后形态：

```java
Map<String, Object> result = pythonClient.updatePlanProgress(planId, planData, stepsData,
        body.getStep_id(), body.getStep_order() != null ? body.getStep_order() : 0,
        body.getStatus(), body.getActivity_type(), body.getScore(),
        body.getDuration_minutes(), masteries);

// ── 新增：消费 mastery_updates 并落库（P2 Task 6）──
persistMasteryUpdates(userId, plan.getCourseId(), result);

return Result.ok(result);
```

`persistMasteryUpdates` 的语义见 §三 A。

### 2.3 落点二 — `GraphController.updateMasteries`

在 `:67` 取到 `result` 之后、`:68 return` 之前插入。**此处必须先与入参 `masteries` 做差**，原因见 §三 B。

```java
Map<String, Object> result = pythonClient.updateMasteries(courseId, masteries, request.getEvents());

// ── 新增：仅落库发生变化的节点（P2 Task 6）──
persistChangedMasteries(userId, courseId, masteries, result);

return Result.ok(result);
```

---

## 三、两条链路的 payload 形状**不同**（本文件最容易踩错的地方）

Python 侧两条链路返回的键路径与结构**不是同一套**，不能共用一个解析函数。

### A. progress 链路 —— diff 形式，且可能缺键

来源 `ai-service/app/centers/plan_center.py:510-517`（构造）、`:543`（返回）：

```python
mastery_updates = {}
if knowledge_node_id:                       # ← knowledge_node_id 为空时整条省略
    mastery_updates[knowledge_node_id] = {
        "old_mastery": old_mastery,
        "new_mastery": new_mastery,
        "delta": round(new_mastery - old_mastery, 2),
        "event_type": event_type,
    }
```

Java 取数路径：

```
result["mastery_updates"]                       // Map<String, Map<String,Object>>，可能为 {}
  └─ <node_id>
       ├─ old_mastery   float   ← 不要落库
       ├─ new_mastery   float   ← ★ 只落这个
       ├─ delta         float   ← 不要落库
       └─ event_type    str
```

**必须做的事**：
1. `mastery_updates` 可能是空 map → 先判空。
2. `knowledge_node_id` 为空时**整条 entry 不存在** → 只能遍历实际存在的 key，不能按 step 反推。
3. 只取 `new_mastery`，忽略 `old_mastery` / `delta`。

### B. graph 链路 —— 全量 map，不是 diff

来源 `ai-service/app/centers/graph_center.py:93-109`：

```python
async def update_masteries(self, *, course_id, masteries, events) -> dict:
    """按学习事件累积掌握度。Python 只计算，Java 自行持久化结果。"""
    result = dict(masteries)                # ← 起点就是全量入参
    for event in events:
        node_id = event["node_id"]
        current = result.get(node_id, 0.0)
        result[node_id] = plan_service.update_mastery(current, event["event_type"], event.get("score"))
    return {"masteries": result}
```

Java 取数路径：

```
result["masteries"]        // Map<String, Float>，**包含全部节点**，不只是变化的
  └─ <node_id> -> float    // 未受事件影响的节点，值 == 入参原值
```

**因此绝不能「遍历全量直接 upsert」**：那样每次调用都会把**每一个**节点行重写一遍，把 `last_review_at` 全部刷成当前时间、并触发无意义的 UPDATE。正确做法是**与入参 `masteries` 求差**：

```java
// 伪代码，语义冻结于此：只落 value 发生变化的 node
Map<String, Float> before = masteries;              // 调用前 buildMasteryMap 的结果，已在手
Map<String, Float> after  = (Map<String, Float>) result.get("masteries");
for (entry : after) {
    Float prev = before.get(entry.getKey());
    if (prev == null || Float.compare(prev, entry.getValue()) != 0) {
        masteryService.upsert(userId, entry.getKey(), courseId, entry.getValue(), /* reviewCount 见 §四.2 */);
    }
}
```

---

## 四、必须避开的三个坑

### 1. `upsert` 的 WHERE 只按 userId + nodeId，**不带 courseId**

`NodeMasteryServiceImpl.upsert` 与 `getByUserIdAndNodeId` 的查询条件是：

```java
.eq(NodeMastery::getUserId, userId)
.eq(NodeMastery::getNodeId, nodeId)
```

后果：**跨课程同名的 nodeId 会互相覆盖**。当前课程白名单只有 `ai_intro`（P2 Task 5），同课程内不会撞；但只要将来放开多课程，nodeId 命名一旦重复就会串数据。

**本 Task 不做修改**（改主键语义超出 P2 范围，且属于 P1 已裁的边界），但**必须知悉**。若 Java 同学认为风险不可接受，正确修法是给 WHERE 加 `.eq(NodeMastery::getCourseId, courseId)`，需单独评估历史数据。

### 2. `reviewCount` 与 `lastReviewAt` 会被**无条件覆盖**

`upsert` 内部对已存在行执行：

```java
existing.setMastery(mastery);
existing.setReviewCount(reviewCount);     // ← 直接覆盖
existing.setLastReviewAt(LocalDateTime.now());  // ← 直接覆盖
```

而 **Python 侧不存在 `new_review_count` 这个字段**——两条链路的响应里都没有复习次数。因此：

- `lastReviewAt` 被刷成当前时间是**语义正确**的（该节点刚刚确实被复习/练习了），照常。
- `reviewCount` **没有上游供给**，若传 `null` 会把已有计数抹掉。**建议**：先 `getByUserIdAndNodeId` 取现值，`reviewCount` 传 `existing != null ? existing.getReviewCount() : 0`，即「保持原值、首次为 0」。

> 这是本任务唯一的语义缺口，Python 侧不打算补（复习计数的口径属于 Java 数据模型，不在 P1/P2 契约内）。**按建议处理，或由 Java 同学另立口径**。

### 3. 只落 `new_mastery` / 变化后的 value，永不落 `old_mastery`

`old_mastery` 与 `delta` 是**计算过程的中间量**，用于展示与审计，不是状态。落库真源只有「算完之后的值」。

---

## 五、验收（A7）

**门禁 A7**：真实 HTTP 调用 `POST /api/plans/{planId}/progress` 之后，`node_masteries` 表确有写入。

**执行前置**：需要 Java 后端 + 数据库 + 前端登录态三者齐备。**Python 侧无法执行**。

**未就绪时的处理**（依据 P2 §〇 问题 4 证据分级 ③）：在验收记录里标注 **「未执行」**，并注明原因「取决于 Java 落地」。**不得**用离线契约测试冒充 A7。

**可执行的核验步骤**（Java 侧就绪后照抄）：

```bash
# 1. 调用前：记录该用户 + 该课程的 node_masteries 行
#    期望：目标 node_id 无行，或 mastery 为旧值

# 2. 触发一次带 knowledge_node_id 的进度上报
curl -X POST "http://localhost:8080/api/plans/<planId>/progress" \
  -H "Authorization: <token>" -H "Content-Type: application/json" \
  -d '{"step_id":<id>,"step_order":<n>,"status":"completed","activity_type":"exercise","score":80}'

# 3. 调用后：再查 node_masteries
#    期望：目标 node_id 有行，mastery == 响应里 data.mastery_updates.<node_id>.new_mastery
#          last_review_at 已更新；review_count 未被抹成 null
```

**辅助观察点**：响应体的 `data.mastery_updates` 必须**原样保留**——本次改动是「旁路落库」，不得改变对前端的响应契约。

---

## 六、回滚

- 回滚方式：revert Java 侧本次单 commit。
- **已写入的 `node_masteries` 行不删除**（P2 §十 明确）：它本就是掌握度真源，回滚只停止「新的自动写入」，不清历史。
- 回滚后行为 == 缺口①状态（Python 照算，Java 不落库），系统仍可运行。

---

## 七、Python 侧已就绪的证据

本次交接依赖的 Python 契约**已由测试钉住**，Java 同学可据此核对：

| 契约点 | 钉住它的位置 |
|--------|--------------|
| progress 返回含 `mastery_updates`，且 entry 为 `old/new/delta/event_type` | `ai-service/tests/test_plan_endpoints_api_contract.py` |
| `knowledge_node_id` 为空 → `mastery_updates` 整条省略 | `plan_center.py:510-517` 的 `if knowledge_node_id:` 守卫 |
| graph 返回 `{"masteries": <全量 map>}` | `ai-service/internal_api/graph.py:95-100` 路由 + `graph_center.py:109` |
| `new_mastery` 由 `update_mastery(old, event_type, score)` 算出，口径冻结 | `ai-service/app/services/mastery_scale.py`（P1 §3.4）+ P2 Task 1 |

---

## 八、明确不做

1. **不改 Java 任何掌握度算法**——Java 只落 Python 算出的值（P2 §五 边界规则 2）。
2. **不给 `upsert` 加 courseId 查询条件**（见 §四.1，超范围，另行评估）。
3. **不在 Python 侧补 `new_review_count`**（见 §四.2）。
4. **不改前端**、不改响应契约。
5. **不代做 Java 改动**——本文件是交接清单，落地由 Java 同学执行。

---

## 九、交接确认清单（Java 同学勾选）

- [ ] 复用两个 Controller 已存在的 `masteryService` 字段（**未**新增第二个 `INodeMasteryService` 字段）
- [ ] `updateProgress` 在 `:310 return` 前落库，遍历 `mastery_updates` 且只取 `new_mastery`
- [ ] `updateMasteries` 在 `:68 return` 前落库，**与入参求差**后只落变化节点
- [ ] `reviewCount` 处理已决（保原值 or 新口径，二选一并写明）
- [ ] 已确认知悉 §四.1 的 nodeId-only 覆盖风险
- [ ] A7 真实 HTTP 已执行 / 已标注「未执行（取决于 Java 落地）」
