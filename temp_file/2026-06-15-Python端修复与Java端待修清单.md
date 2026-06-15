# Python 端修复与 Java 端待修清单

> 生成日期：2026-06-15  
> 分支：`后端改造分支`（HEAD = ddec366）  
> 范围：自 ddec366 以来未提交工作树的 Python AI 服务 ↔ Java 后端集成 gaps  

---

## 一、本次已修复（Python 端）

| # | 问题 | 修复位置 | 修复方式 | 验证 |
|---|------|----------|----------|------|
| 1 | `graph_service.py:1018` 中 `prereqs` 未定义，调用 `/internal/graph/layered` 必炸 | `ai-service/app/services/graph_service.py` | 在循环内补 `prereqs = predecessors.get(nid, [])` | `python3 -m py_compile` 通过 |
| 2 | `embeddings.py` 直接 `import numpy as np`，但 `requirements.txt` 未声明 | `ai-service/requirements.txt` | 添加 `numpy>=1.26.0` | 文件解析通过 |
| 3 | Java 调用 `POST /internal/plans/status`，Python 路由为 `POST /internal/plans/{plan_id}/status` | `ai-service/internal_api.py` | 新增兼容路由 `@router.post("/plans/status")`，从 `body.plan.id` 提取 plan_id 后复用核心逻辑 | `python3 -m py_compile` 通过 |

### 1.1 修复 #3 的代码说明

原 Python 路由：

```python
@router.post("/plans/{plan_id}/status")
async def get_plan_status(plan_id: int, body: PlanStatusRequest):
    ...
```

新增兼容层：

```python
@router.post("/plans/{plan_id}/status")
async def get_plan_status(plan_id: int, body: PlanStatusRequest):
    """查询计划状态（含软着陆触发检测）。Java 传入 plan + steps 数据。"""
    return await _get_plan_status_core(plan_id, body)


@router.post("/plans/status")
async def get_plan_status_legacy(body: PlanStatusRequest):
    """兼容旧路径：/internal/plans/status（无 path 参数 plan_id）。"""
    plan_id = 0
    if body.plan and isinstance(body.plan.get("id"), int):
        plan_id = body.plan["id"]
    return await _get_plan_status_core(plan_id, body)


async def _get_plan_status_core(plan_id: int, body: PlanStatusRequest):
    ...  # 原 get_plan_status 的核心逻辑
```

**注意**：核心逻辑仍从 `body.plan` 和 `body.steps` 读取数据，路径参数 `plan_id` 目前仅用于日志/追踪，因此旧路径和无 plan_id 的调用均可用。

---

## 二、Java 端仍需修复

以下问题属于 Java `PythonClient.java` 与 Python 端点契约不匹配，**必须由 Java 后端同学修改**。

| # | Java 方法 | 当前 Java 调用 | Python 端点 | 需要修改的内容 | 严重程度 |
|---|-----------|---------------|-------------|----------------|----------|
| J1 | `getProfileStatus` | `GET /internal/profile/workflow/status?user_id=X` | `POST /internal/profile/workflow/status` | **HTTP 方法改为 POST**，请求体传 `{user_id, student_profile}` | 🔴 高 |
| J2 | `getLearningPath` | `GET /internal/path/{userId}` | `POST /internal/path/{student_id}` | **HTTP 方法改为 POST**，请求体传 `{user_id, course_id, topic, student_profile}` | 🔴 高 |
| J3 | `getReviewSchedule` | `GET /internal/plans/{planId}/review-schedule?user_id=X&days_ahead=N` | `POST /internal/plans/{planId}/review-schedule` | **HTTP 方法改为 POST**，请求体传 `{steps, days_ahead}`，不再使用 query 参数 | 🔴 高 |
| J4 | `getConversationSummary` | `GET /internal/conversations/{id}/summary?user_id=X&course_id=Y` | `POST /internal/conversations/{id}/summary` | **HTTP 方法改为 POST**，请求体传 `{messages, course_id}` | 🔴 高 |
| J5 | `regressionCheck` | `POST /internal/plans/{planId}/regression-check` 请求体 `{user_id, answers}` | `POST /internal/plans/{planId}/regression-check` | 路径已匹配，但请求体需补 `{plan, steps, days_idle}`，不能只传 `user_id` 和 `answers` | 🟡 中 |

### J1 `getProfileStatus` 修改示例

```java
// 旧代码
return doGet(BASE_URL + "/profile/workflow/status?user_id=" + userId);

// 新代码
Map<String, Object> request = new HashMap<>();
request.put("user_id", userId);
request.put("student_profile", studentProfile != null ? studentProfile : new HashMap<>());
return doPost(BASE_URL + "/profile/workflow/status", request);
```

### J2 `getLearningPath` 修改示例

```java
// 旧代码
return doGet(BASE_URL + "/path/" + userId);

// 新代码
Map<String, Object> request = new HashMap<>();
request.put("user_id", userId);
request.put("course_id", courseId);
request.put("topic", topic);
request.put("student_profile", studentProfile != null ? studentProfile : new HashMap<>());
return doPost(BASE_URL + "/path/" + userId, request);
```

### J3 `getReviewSchedule` 修改示例

```java
// 旧代码
return doGet(BASE_URL + "/plans/" + planId + "/review-schedule?user_id=" + userId + "&days_ahead=" + daysAhead);

// 新代码
Map<String, Object> request = new HashMap<>();
request.put("steps", steps);
request.put("days_ahead", daysAhead);
return doPost(BASE_URL + "/plans/" + planId + "/review-schedule", request);
```

### J4 `getConversationSummary` 修改示例

```java
// 旧代码
return doGet(BASE_URL + "/conversations/" + conversationId + "/summary?user_id=" + userId + "&course_id=" + courseId);

// 新代码
Map<String, Object> request = new HashMap<>();
request.put("messages", messages);
request.put("course_id", courseId);
return doPost(BASE_URL + "/conversations/" + conversationId + "/summary", request);
```

### J5 `regressionCheck` 修改示例

```java
// 旧代码
Map<String, Object> request = new HashMap<>();
request.put("user_id", userId);
request.put("answers", answers != null ? answers : new ArrayList<>());
return doPost(BASE_URL + "/plans/" + planId + "/regression-check", request);

// 新代码
Map<String, Object> request = new HashMap<>();
request.put("user_id", userId);
request.put("answers", answers != null ? answers : new ArrayList<>());
request.put("plan", plan);        // 计划元数据 {id, user_id, status, ...}
request.put("steps", steps);      // 步骤列表
request.put("days_idle", daysIdle); // 空闲天数
return doPost(BASE_URL + "/plans/" + planId + "/regression-check", request);
```

---

## 三、新功能未开发（本次不涉及修改）

以下两个端点 Java 已调用，但 Python 端**尚未实现**。按当前产品规划，它们属于后续功能，本次只记录不修复。

| # | Java 方法 | Java 调用 | Python 状态 | 说明 |
|---|-----------|-----------|-------------|------|
| N1 | `getUserDashboard` | `GET /internal/user/dashboard?user_id=X&course_id=Y` | 端点不存在 | 仪表盘数据聚合。待练习模块整体方案确定后再实现 |
| N2 | `endConversation` | `POST /internal/conversations/{id}/end?user_id=X&course_id=Y` | 端点不存在 | 会话结束 + 总结压缩。需先明确对话归档和总结触发策略 |

---

## 四、Python ↔ Java 端点映射总表

基于 `PythonClient.java` 22 个方法 vs `ai-service/internal_api.py` 当前路由。

| Java 方法 | HTTP | Java URL | Python 路由 | 状态 |
|-----------|------|----------|-------------|------|
| `unifiedChatStream` | POST | `/internal/api/chat` | `POST /internal/api/chat` | ✅ 已匹配 |
| `buildProfileStream` | POST | `/internal/profile/chat` | `POST /internal/profile/chat` | ✅ 已匹配 |
| `generateResourcesStream` | POST | `/internal/resources/generate` | `POST /internal/resources/generate` | ✅ 已匹配 |
| `tutorChatStream` | POST | `/internal/tutor/chat` | `POST /internal/tutor/chat` | ✅ 已匹配 |
| `generateExercisesStream` | POST | `/internal/exercise/generate` | `POST /internal/exercise/generate` | ✅ 已匹配 |
| `getProfileStatus` | GET | `/internal/profile/workflow/status?user_id=X` | `POST /internal/profile/workflow/status` | ❌ J1 |
| `getLearningPath` | GET | `/internal/path/{userId}` | `POST /internal/path/{student_id}` | ❌ J2 |
| `gradeExercise` | POST | `/internal/exercise/grade` | `POST /internal/exercise/grade` | ✅ 已匹配 |
| `getEvaluationReport` | POST | `/internal/evaluation/report` | `POST /internal/evaluation/report` | ✅ 已匹配 |
| `exportPptx` | POST | `/internal/resources/export-pptx` | `POST /internal/resources/export-pptx` | ✅ 已匹配 |
| `solveStream` | POST | `/internal/solve` | `POST /internal/solve` | ✅ 已匹配 |
| `getKnowledgeGraph` | POST | `/internal/knowledge-graph/{courseId}` | `POST /internal/knowledge-graph/{course_id}` | ✅ 已匹配 |
| `getNodeCard` | POST | `/internal/knowledge-graph/{courseId}/node/{nodeId}` | `POST /internal/knowledge-graph/{course_id}/node/{node_id}` | ✅ 已匹配 |
| `createPlanFromPath` | POST | `/internal/plans/create-from-path` | `POST /internal/plans/create-from-path` | ✅ 已匹配（topic 默认空字符串） |
| `getPlanStatus` | POST | `/internal/plans/status` | `POST /internal/plans/status`（新增兼容）+ `POST /internal/plans/{plan_id}/status` | ✅ 已修复 |
| `regressionCheck` | POST | `/internal/plans/{planId}/regression-check` | `POST /internal/plans/{plan_id}/regression-check` | 🟡 J5 |
| `getReviewSchedule` | GET | `/internal/plans/{planId}/review-schedule?...` | `POST /internal/plans/{plan_id}/review-schedule` | ❌ J3 |
| `inquiryResolveStream` | POST | `/internal/inquiry/resolve` | `POST /internal/inquiry/resolve` | ✅ 已匹配 |
| `getUserDashboard` | GET | `/internal/user/dashboard?...` | 不存在 | ⚪ N1 |
| `getConversationSummary` | GET | `/internal/conversations/{id}/summary?...` | `POST /internal/conversations/{id}/summary` | ❌ J4 |
| `endConversation` | POST | `/internal/conversations/{id}/end?...` | 不存在 | ⚪ N2 |
| `errorAnalysis` | POST | `/internal/exercise/error-analysis` | `POST /internal/exercise/error-analysis` | ✅ 已匹配 |

---

## 五、建议的 Java 端修改优先级

1. **P0（立即）**：J1 ~ J4 四个 GET→POST 修改。这四个端点一旦对接到当前 Python 服务，会直接 405 Method Not Allowed。
2. **P1（本周）**：J5 `regressionCheck` 补 `plan/steps/days_idle`。当前调用不会 500，但会返回 "计划不存在"，功能不可用。
3. **P2（后续迭代）**：N1 `user/dashboard`、N2 `conversations/end`。需要产品方案明确后再开发对应 Python 端点。

---

## 六、Python 端后续仍需关注

| 问题 | 位置 | 说明 |
|------|------|------|
| `PathAgent` 返回 topic 裁剪子图 | `ai-service/app/agents/path_agent.py` | 已确认是有意设计，Java 端不应假设拿到完整骨架 |
| `ChatCenter` 默认关闭 | `ai-service/app/centers/chat_center.py` | `USE_CENTER_PIPELINE` 默认 `false`，旧集成路径仍可用 |
| 新 SSE 事件类型 | `ai-service/app/events/types.py` | `CENTER_START/CENTER_END/INQUIRY` 已转发到前端，Java 端可暂不处理 |

---

## 七、验证命令

```bash
# Python 语法检查
python3 -m py_compile ai-service/internal_api.py ai-service/app/services/graph_service.py

# requirements.txt 解析检查
python3 -c "import pkg_resources; list(pkg_resources.parse_requirements(open('ai-service/requirements.txt').read()))"
```

---

*本文档由 AI Agent 根据当前分支未提交改动生成，用于指导 Java 后端同学完成对接修复。*
