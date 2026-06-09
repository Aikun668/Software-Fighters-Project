# AI 服务 ↔ Java 后端 API 对接文档

> **用途**：Java 后端团队据此实现 REST API，供 Python AI 服务调用
> **环境变量**：Python 端通过 `JAVA_API_BASE_URL` 配置 Java 后端地址（默认 `http://localhost:8080/api`）
> **最后更新**：2026-06-06

---

## 统一响应格式

所有接口统一返回以下 JSON 结构：

```json
{
  "code": 0,
  "message": "ok",
  "data": { ... }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | int | 0 = 成功，非 0 = 错误（自定义错误码） |
| `message` | string | 提示信息 |
| `data` | any | 业务数据，错误时为 null |

---

## 1. Health

### `GET /health`

Java 服务健康检查。Python 端 `/health` 端点会 ping 此接口判断连通性。

**响应 data**：`{ "status": "ok" }`

---

## 2. Conversation（会话）

### `POST /api/conversations`

创建新会话。

**请求体**：
```json
{
  "user_id": 1
}
```

**响应 data**：
```json
{
  "id": 100,
  "user_id": 1,
  "title": "新对话",
  "status": "active",
  "created_at": "2026-06-06T10:00:00"
}
```

---

### `GET /api/conversations/{conversation_id}?user_id=1`

获取指定会话详情。

**响应 data**：同上（含 `summary` 字段用于摘要展示）

---

### `PUT /api/conversations/{conversation_id}`

更新会话（标题、状态、摘要等）。

**请求体**（全部可选字段）：
```json
{
  "title": "微积分学习讨论",
  "status": "archived",
  "summary": "本会话讨论了极限与导数的核心概念..."
}
```

**响应 data**：更新后的完整会话对象

---

### `GET /api/conversations/{conversation_id}/messages?mode=tutor&limit=50`

加载会话消息历史。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `mode` | string | 否 | 按对话模式过滤（`tutor` / `path` / `resource` 等） |
| `limit` | int | 否 | 返回条数上限，默认 50 |

**响应 data**（数组）：
```json
[
  {
    "id": 1,
    "conversation_id": 100,
    "role": "user",
    "content": "什么是导数？",
    "mode": "tutor",
    "created_at": "2026-06-06T10:01:00"
  },
  {
    "id": 2,
    "conversation_id": 100,
    "role": "assistant",
    "content": "导数是函数在某一点的瞬时变化率...",
    "mode": "tutor",
    "created_at": "2026-06-06T10:01:05"
  }
]
```

---

### `GET /api/conversations/{conversation_id}/messages/raw?offset=0&limit=200`

加载消息原始数据（不分 mode 过滤，用于压缩/摘要场景）。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `offset` | int | 否 | 偏移量，默认 0 |
| `limit` | int | 否 | 返回条数上限，默认 200 |

**响应 data**：同上格式的数组

---

### `POST /api/conversations/{conversation_id}/messages`

批量保存用户消息和 AI 回复（一个事务内完成 2 条 INSERT + 更新会话时间）。

**请求体**：
```json
{
  "user_message": "什么是导数？",
  "assistant_message": "导数是函数在某一点的瞬时变化率...",
  "user_mode": "tutor",
  "assistant_mode": "tutor"
}
```

**响应 data**：`{ "saved": 2 }`

---

## 3. StudentProfile（学生画像）

### `GET /api/profiles/{user_id}`

获取学生画像。

**响应 data**：
```json
{
  "user_id": 1,
  "profile_dict": {
    "knowledge": { "calculus": 0.6, "linear_algebra": 0.3 },
    "style": "visual",
    "pace": "moderate",
    "entries": [
      { "concept": "导数", "mastery": 0.75, "confidence": 0.8 },
      { "concept": "积分", "mastery": 0.4, "confidence": 0.5 }
    ]
  },
  "last_extracted_msg_index": 42,
  "created_at": "2026-06-01T08:00:00",
  "updated_at": "2026-06-06T12:00:00"
}
```

> `profile_dict` 是自由格式 JSON，具体结构由 AI 端定义和维护。`last_extracted_msg_index` 用于增量画像提取的断点续传。

---

### `PUT /api/profiles/{user_id}`

全量写入/覆盖画像（upsert 语义）。

**请求体**：
```json
{
  "profile_dict": { "knowledge": {...}, "style": "visual", ... },
  "last_extracted_msg_index": 42
}
```

**响应 data**：更新后的完整 profile 对象

---

### `POST /api/profiles/{user_id}`

部分更新画像字段。

**请求体**（全部可选）：
```json
{
  "profile_dict": { "knowledge": {...} },
  "last_extracted_msg_index": 50
}
```

**响应 data**：更新后的完整 profile 对象

---

## 4. LearningPlan（学习计划）+ PlanStep（计划步骤）

### `POST /api/plans`

创建学习计划（含步骤列表，一个事务内完成）。

**请求体**：
```json
{
  "user_id": 1,
  "course_id": "calculus_101",
  "title": "微积分学习计划",
  "steps": [
    {
      "node_id": "node_01",
      "topic": "函数与极限",
      "order": 0,
      "status": "pending",
      "node_type": "learn",
      "depth": 0
    },
    {
      "node_id": "node_02",
      "topic": "导数定义",
      "order": 1,
      "status": "locked",
      "node_type": "learn",
      "depth": 0
    }
  ]
}
```

**step 字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `node_id` | string | 知识图谱节点 ID |
| `topic` | string | 知识点名称 |
| `order` | int | 排序序号（从 0 开始） |
| `status` | string | pending / in_progress / completed / locked |
| `node_type` | string | learn / practice / review |
| `depth` | int | 在知识图谱中的深度层级 |

**响应 data**：
```json
{
  "id": 200,
  "user_id": 1,
  "course_id": "calculus_101",
  "title": "微积分学习计划",
  "status": "in_progress",
  "total_steps": 2,
  "completed_steps": 0,
  "steps": [ ... ]
}
```

---

### `GET /api/plans/{plan_id}?user_id=1`

获取计划详情（含步骤列表）。

**响应 data**：同上格式

---

### `PUT /api/plans/{plan_id}`

更新计划（标题、状态等）。

**请求体**（全部可选）：
```json
{
  "title": "新标题",
  "status": "paused"
}
```

---

### `GET /api/plans/{plan_id}/steps`

获取计划的所有步骤（按 order 排序）。

**响应 data**（数组）：
```json
[
  {
    "id": 1001,
    "plan_id": 200,
    "node_id": "node_01",
    "topic": "函数与极限",
    "order": 0,
    "status": "completed",
    "node_type": "learn",
    "depth": 0
  }
]
```

---

### `POST /api/plans/{plan_id}/steps`

在指定位置插入新步骤（并自动调整后续步骤的 order）。

**请求体**：
```json
{
  "node_id": "node_03",
  "topic": "导数应用",
  "order": 2,
  "status": "locked",
  "node_type": "learn",
  "depth": 0
}
```

---

### `PUT /api/plan-steps/{step_id}`

更新单个步骤。

**请求体**（全部可选）：
```json
{
  "status": "completed",
  "order": 1
}
```

---

### `POST /api/plans/{plan_id}/steps/shift`

将指定 order 之后的所有步骤 order +1（用于在中间插入步骤时腾出位置）。

**请求体**：
```json
{
  "after_order": 1
}
```

---

### `POST /api/plans/{plan_id}/steps/lock-successors`

锁定指定 node 的所有后继步骤。Java 端需根据知识图谱依赖关系查找后继节点。

**请求体**：
```json
{
  "node_id": "node_05"
}
```

**响应 data**：
```json
{
  "locked_ids": [1003, 1004, 1005]
}
```

---

### `POST /api/plans/node-status-change`

处理节点状态变更的复杂事务（Java 端需原子执行以下操作）：

1. 查找用户当前 `in_progress` 状态的学习计划
2. 查找该 node_id 对应的 PlanStep
3. 遍历图骨架找后继节点
4. 更新后继节点步骤为 `locked`
5. 将当前步骤之后的步骤 order+1 腾出空位
6. 插入一条复习步骤（review 类型）
7. 更新计划总步骤数 +1

**请求体**：
```json
{
  "user_id": 1,
  "node_id": "node_05",
  "old_status": "in_progress",
  "new_status": "completed",
  "plan_id": 200
}
```

**响应 data**：
```json
{
  "plan_id": 200,
  "updated_step_id": 1005,
  "locked_step_ids": [1006, 1007],
  "new_review_step_id": 1008
}
```

---

## 5. NodeMastery（节点掌握度）

### `GET /api/node-masteries?user_id=1&course_id=calculus_101`

获取用户在指定课程的所有节点掌握度。

**响应 data**（数组）：
```json
[
  { "node_id": "node_01", "mastery": 0.85, "review_count": 3, "last_review_at": "2026-06-05T14:00:00" },
  { "node_id": "node_02", "mastery": 0.40, "review_count": 1, "last_review_at": "2026-06-03T10:00:00" }
]
```

---

### `GET /api/node-masteries/{node_id}?user_id=1`

获取单个节点的掌握度详情。

**响应 data**：
```json
{
  "node_id": "node_01",
  "user_id": 1,
  "course_id": "calculus_101",
  "mastery": 0.85,
  "review_count": 3,
  "last_review_at": "2026-06-05T14:00:00"
}
```

---

### `PUT /api/node-masteries/{node_id}`

写入/更新节点掌握度（upsert 语义）。

**请求体**：
```json
{
  "user_id": 1,
  "course_id": "calculus_101",
  "mastery": 0.85,
  "review_count": 3
}
```

---

### `GET /api/node-masteries/distribution?user_id=1&course_id=calculus_101`

获取掌握度分布统计。

**响应 data**：
```json
{
  "mastered": 12,
  "in_progress": 8,
  "weak": 5,
  "overall_pct": 0.62
}
```

---

## 6. LearningActivity（学习活动记录）

### `POST /api/learning-activities`

创建一条学习活动记录。

**请求体**：
```json
{
  "user_id": 1,
  "plan_id": 200,
  "step_id": 1005,
  "activity_type": "exercise",
  "duration_minutes": 15,
  "score": 0.9
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | int | 是 | 用户 ID |
| `plan_id` | int | 是 | 所属学习计划 ID |
| `step_id` | int | 是 | 所属步骤 ID |
| `activity_type` | string | 是 | exercise / review / study |
| `duration_minutes` | int | 否 | 耗时（分钟），默认 0 |
| `score` | float | 否 | 得分 (0.0-1.0) |

---

### `GET /api/learning-activities?user_id=1&limit=20`

获取最近的学习活动记录列表。

**响应 data**（数组）：
```json
[
  {
    "id": 1,
    "user_id": 1,
    "plan_id": 200,
    "step_id": 1005,
    "activity_type": "exercise",
    "duration_minutes": 15,
    "score": 0.9,
    "topic": "导数定义",
    "created_at": "2026-06-06T15:00:00"
  }
]
```

> `topic` 字段来自 PlanStep 的 JOIN，Java 端需关联查询。

---

### `GET /api/learning-activities/stats?user_id=1`

获取用户学习活动统计摘要。

**响应 data**：
```json
{
  "total_sessions": 42,
  "total_minutes": 630,
  "first_date": "2026-05-01",
  "last_date": "2026-06-06"
}
```

---

### `GET /api/learning-activities/score-trend?user_id=1&days=30`

获取用户得分趋势（按日期聚合）。

**响应 data**（数组）：
```json
[
  { "date": "2026-06-01", "avg_score": 0.75, "count": 3 },
  { "date": "2026-06-02", "avg_score": 0.82, "count": 2 }
]
```

---

### `GET /api/learning-activities/count-exercises?user_id=1`

获取用户总练习次数。

**响应 data**：
```json
{
  "count": 128
}
```

---

## 7. Resource（学习资源）

### `POST /api/resources`

创建一条学习资源。

**请求体**：
```json
{
  "user_id": 1,
  "type": "path_step",
  "topic": "导数定义",
  "title": "导数定义",
  "content_json": {
    "order": 0,
    "status": "pending",
    "preview": "导数的基本定义与几何意义"
  }
}
```

**响应 data**：
```json
{
  "id": 500
}
```

---

### `POST /api/resources/batch`

批量创建资源（可选优化端点，减少网络往返）。

**请求体**：
```json
{
  "resources": [
    { "user_id": 1, "type": "flash_text", "topic": "导数", "title": "导数闪卡1", "content_json": {...} },
    { "user_id": 1, "type": "flash_text", "topic": "导数", "title": "导数闪卡2", "content_json": {...} }
  ]
}
```

**响应 data**：
```json
{
  "ids": [501, 502]
}
```

---

## 8. LearningRecord（学习记录）

### `POST /api/learning-records`

创建一条学习进度记录。

**请求体**：
```json
{
  "user_id": 1,
  "resource_id": 500,
  "progress": 0.0
}
```

**响应 data**：
```json
{
  "id": 600
}
```

---

## 9. 聚合查询

### `GET /api/aggregations/topic-mastery?user_id=1`

按 topic 聚合用户掌握度（JOIN PlanStep + LearningPlan，用于 Dashboard 图表）。

**响应 data**（数组）：
```json
[
  { "topic": "函数与极限", "mastery_avg": 0.85, "step_count": 3 },
  { "topic": "导数定义", "mastery_avg": 0.60, "step_count": 2 }
]
```

---

## 附录 A：环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `JAVA_API_BASE_URL` | Java 后端 API 基地址 | `http://localhost:8080/api` |

Python 端 `JavaApiClient` 类从该环境变量读取地址，并在每个 HTTP 请求头中设置 `Content-Type: application/json`，超时时间 10 秒。

---

## 附录 B：错误码约定

| code | 含义 |
|------|------|
| 0 | 成功 |
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

> Python 端对 HTTP 4xx/5xx 和超时均做降级处理（返回安全默认值如空列表/None/0），不阻塞主流程，但会记录 warning 日志。

---

## 附录 C：数据库表字段参考

以下为 10 张表的完整字段定义，供 Java 端设计 Entity 时参考：

### conversations
| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 自增主键 |
| user_id | BIGINT | 用户 ID |
| title | VARCHAR(255) | 对话标题 |
| status | VARCHAR(20) | active / archived |
| summary | TEXT | AI 生成的对话摘要 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

### messages
| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 自增主键 |
| conversation_id | BIGINT FK | 所属会话 |
| role | VARCHAR(20) | user / assistant |
| content | TEXT | 消息内容 |
| mode | VARCHAR(20) | tutor / path / resource 等 |
| created_at | DATETIME | 创建时间 |

### student_profiles
| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | BIGINT PK | 用户 ID |
| profile_dict | JSON | 画像数据（自由格式） |
| last_extracted_msg_index | INT | 最后提取的消息索引 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

### learning_plans
| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 自增主键 |
| user_id | BIGINT | 用户 ID |
| course_id | VARCHAR(100) | 课程 ID |
| title | VARCHAR(255) | 计划标题 |
| status | VARCHAR(20) | in_progress / completed / paused |
| total_steps | INT | 总步骤数 |
| completed_steps | INT | 已完成步骤数 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

### plan_steps
| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 自增主键 |
| plan_id | BIGINT FK | 所属计划 |
| node_id | VARCHAR(100) | 知识图谱节点 ID |
| topic | VARCHAR(255) | 知识点名称 |
| order | INT | 排序序号 |
| status | VARCHAR(20) | pending / in_progress / completed / locked |
| node_type | VARCHAR(20) | learn / practice / review |
| depth | INT | 图谱深度层级 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

### node_masteries
| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 自增主键 |
| user_id | BIGINT | 用户 ID |
| node_id | VARCHAR(100) | 知识图谱节点 ID |
| course_id | VARCHAR(100) | 课程 ID |
| mastery | FLOAT | 掌握度 (0.0-1.0) |
| review_count | INT | 复习次数 |
| last_review_at | DATETIME | 最近复习时间 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

### learning_activities
| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 自增主键 |
| user_id | BIGINT | 用户 ID |
| plan_id | BIGINT | 所属计划 ID |
| step_id | BIGINT | 所属步骤 ID |
| activity_type | VARCHAR(20) | exercise / review / study |
| duration_minutes | INT | 耗时（分钟） |
| score | FLOAT | 得分 |
| created_at | DATETIME | 创建时间 |

### resources
| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 自增主键 |
| user_id | BIGINT | 用户 ID |
| type | VARCHAR(50) | flash_text / flash_image / path_step 等 |
| topic | VARCHAR(255) | 知识点名称 |
| title | VARCHAR(255) | 资源标题 |
| content_json | JSON | 资源内容（自由格式） |
| created_at | DATETIME | 创建时间 |

### learning_records
| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 自增主键 |
| user_id | BIGINT | 用户 ID |
| resource_id | BIGINT FK | 关联资源 |
| progress | FLOAT | 学习进度 (0.0-1.0) |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |
