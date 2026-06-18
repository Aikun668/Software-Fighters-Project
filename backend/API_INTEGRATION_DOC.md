# 前后端对接文档 — 智能学习平台

> 后端地址: `http://localhost:8080`
> Python AI: `http://localhost:8001/internal`（Java 代理，前端不直连）
> 文档更新时间: 2026-06-16

---

## 0. 前置说明

### 0.1 通用响应格式

所有非 SSE 接口统一返回:

```json
{
  "code": 0,           // 0=成功, 400=业务失败
  "message": "ok",     // 提示信息
  "data": {}           // 业务数据, 分页时为 { "list": [...], "total": N }
}
```

### 0.2 认证方式

- 登录后后端在 **Response Header** 中返回 `authorization` 字段(值为 token 字符串)
- 前端需保存该 token,后续所有请求在 **Request Header** 中携带 `Authorization: Bearer {token}`
- Token 有效期: 25 天(无操作自动续期)
- 公开接口(无需 token): 获取验证码、注册、登录

### 0.3 SSE 接口注意

以下接口返回 **流式 SSE** (`text/event-stream`)，**不是 JSON**:
- 统一对话 `/api/chat`、对话辅导 `/api/tutor/chat`
- 资源生成 `/api/resources/generate`、习题生成 `/api/exercise/generate`
- 画像聊天 `/api/profile/chat`、解题 `/api/solve`

前端使用 `fetch` + `ReadableStream` 消费（POST 请求不能用 EventSource）。每个 SSE 事件格式:
```
data: {"type": "token", "content": "文本片段"}\n\n
data: {"type": "done"}\n\n
```

SSE 事件类型: `token`(逐字文本), `progress`(进度), `content`(结构化块), `recommendation`(练习推荐), `profile_update`(画像), `steps`(解题步骤), `confidence`(置信度), `error`, `done`。

### 0.4 当前环境依赖

| 组件 | 地址 | 说明 |
|------|------|------|
| Java 后端 | `localhost:8080` | 本服务 |
| Python AI | `localhost:8001` | AI 引擎,后端代为代理 |
| MySQL | `localhost:3306` | `learning_platform` 库 |
| Redis | `localhost:6379` | Token 缓存 + 验证码 |
| MinIO | `localhost:9000` | 文件存储 |

---

## 1. 用户模块 `/user`

### 1.1 获取图片验证码

```
GET /user/captcha
```

响应:
```json
{
  "code": 0,
  "data": {
    "captchaKey": "uuid-string",
    "captchaImage": "data:image/png;base64,iVBORw0KGgo..."
  }
}
```

| 字段 | 说明 |
|------|------|
| captchaKey | 验证码唯一标识,注册时需回传 |
| captchaImage | Base64 编码的 PNG 图片,可直接用于 `<img src>` |

验证码有效期 **5 分钟**。

### 1.2 注册

```
POST /user/register
Content-Type: application/json
```

请求体:
```json
{
  "username": "张三",
  "password": "abc123",
  "passwordConfirm": "abc123",
  "captchaKey": "uuid-string",
  "captchaCode": "ABCD"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | String | 是 | 用户名,2-20 位 |
| password | String | 是 | 密码,至少 6 位 |
| passwordConfirm | String | 是 | 确认密码,必须一致 |
| captchaKey | String | 是 | 来自 1.1 接口 |
| captchaCode | String | 是 | 用户输入的验证码(不区分大小写) |

响应:
```json
{ "code": 0, "message": "注册成功", "data": null }
```

### 1.3 登录

```
POST /user/login
Content-Type: application/json
```

请求体:
```json
{
  "username": "张三",
  "password": "abc123"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | String | 是 | 用户名 |
| password | String | 是 | 密码 |

响应:
```json
{ "code": 0, "message": "ok", "data": "uuid-token-string" }
```

**注意:** 响应 Header 中同时设置 `authorization` 字段,前端可从 Header 或 Body 取 token 并存储。

---

## 2. 统一对话 `/api/chat` (核心入口)

### 2.1 发起对话 (SSE 流式) — 万能入口

```
POST /api/chat
Content-Type: application/json
Authorization: Bearer {token}
```

**所有模糊输入、自然语言问题全部走这里，AI 内部自动路由。前端不需要判断用户意图。**

请求体（仅含前端传的字段，`user_id`/`student_profile`/`messages` 历史由 Java 从 DB 注入）:
```json
{
  "message": "我想学机器学习,该从哪里开始?",
  "conversation_id": null,
  "mode": "auto",
  "images": [],
  "style": "standard"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| message | String | **是** | 用户自然语言输入，啥都可以写 |
| conversation_id | Long | 否 | 对话ID，续接对话时传入，不传自动创建新会话 |
| mode | String | 否 | `auto`(默认)/`plan`/`resource`/`exercise`，不传默认 auto |
| images | String[] | 否 | 用户上传的图片URL列表（多模态输入） |
| style | String | 否 | `standard`(标准)/`socratic`(苏格拉底式引导)，仅答疑场景生效 |

**SSE 事件流**: `token`(逐字输出) → 可选的 `recommendation`(练习推荐) → `done`

AI 自动判断意图并路由到对应 Agent:
- `tutor` — 答疑对话
- `resource` — 生成学习资源（文档/思维导图/代码等），自动落库
- `exercise` — 生成练习题，自动落库
- `solve` — 分步解题
- `research` — 学习路径规划，自动创建计划

---

## 3. 会话管理 `/api/conversations`

### 3.1 我的会话列表

```
GET /api/conversations/mine
Authorization: Bearer {token}
```

响应:
```json
{
  "code": 0,
  "data": [
    {
      "id": 1,
      "userId": 1,
      "title": "机器学习入门",
      "status": "active",
      "summary": null,
      "createdAt": "2025-06-12 10:30:00",
      "updatedAt": "2025-06-12 11:00:00"
    }
  ]
}
```

### 3.2 创建会话

```
POST /api/conversations
Content-Type: application/json
Authorization: Bearer {token}
```

请求体 (user_id 可不传,后端从 token 取):
```json
{}
```

### 3.3 获取会话详情

```
GET /api/conversations/{id}?userId={userId}
Authorization: Bearer {token}
```

### 3.4 更新会话

```
PUT /api/conversations/{id}
Content-Type: application/json
Authorization: Bearer {token}
```

请求体:
```json
{ "title": "新标题", "status": "archived" }
```

### 3.5 获取会话消息列表

```
GET /api/conversations/{id}/messages?mode=tutor&limit=50
Authorization: Bearer {token}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| mode | String | 否 | 过滤消息模式 |
| limit | int | 否 | 默认 50 |

响应:
```json
{
  "code": 0,
  "data": [
    {
      "id": 1,
      "conversationId": 1,
      "role": "user",
      "content": "什么是机器学习?",
      "mode": "tutor",
      "createdAt": "2025-06-12 10:30:00"
    },
    {
      "id": 2,
      "conversationId": 1,
      "role": "assistant",
      "content": "机器学习是...",
      "mode": "tutor",
      "createdAt": "2025-06-12 10:30:05"
    }
  ]
}
```

### 3.6 获取原始消息(分页)

```
GET /api/conversations/{id}/messages/raw?offset=0&limit=200
Authorization: Bearer {token}
```

### 3.7 手动保存消息

```
POST /api/conversations/{id}/messages
Content-Type: application/json
Authorization: Bearer {token}
```

请求体:
```json
{
  "user_message": "用户问题",
  "assistant_message": "AI回答"
}
```

### 3.8 结束会话

```
POST /api/conversations/{id}/end
Authorization: Bearer {token}
```

后端会调用 AI 生成摘要并归档会话。

### 3.9 删除会话

```
DELETE /api/conversations/{id}
Authorization: Bearer {token}
```

---

## 4. 资源模块 `/api/resources`

### 4.1 生成资源 (SSE 流式)

```
POST /api/resources/generate
Content-Type: application/json
Authorization: Bearer {token}
```

请求体:
```json
{
  "topic": "Python 列表推导式",
  "resource_type": "code"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| topic | String | **是** | 资源主题 |
| resource_type | String | 否 | `document`/`code`/`project`/`mindmap`/`flashcard`/`interactive_diagram`，不传由AI自动判断 |

返回 SSE 流（`progress` → `content` → `done`），完成后资源自动入库。

### 4.2 我的资源列表

```
GET /api/resources/list
Authorization: Bearer {token}
```

### 4.3 按类型筛选资源

```
GET /api/resources/list/{type}
Authorization: Bearer {token}
```

type 可选值: `course_doc`, `mind_map`, `exercise`, `reading`, `code_practice`

### 4.4 资源详情

```
GET /api/resources/{resourceId}
Authorization: Bearer {token}
```

响应:
```json
{
  "code": 0,
  "data": {
    "id": 1,
    "userId": 1,
    "type": "course_doc",
    "topic": "Python 列表推导式",
    "title": "Python 列表推导式详解",
    "contentJson": "{\"sections\":[...]}",
    "filePath": null,
    "createdAt": "2025-06-12 10:30:00"
  }
}
```

`contentJson` 是 JSON 字符串,需前端 `JSON.parse()` 解析。不同 type 的 contentJson 结构不同,由 AI 动态生成。

### 4.5 删除资源

```
DELETE /api/resources/{resourceId}
Authorization: Bearer {token}
```

### 4.6 导出 PPTX

```
POST /api/resources/export-pptx
Content-Type: application/json
Authorization: Bearer {token}
```

请求体:
```json
{
  "title": "课件标题",
  "content_blocks": [
    { "type": "title", "text": "...", "level": 1 },
    { "type": "text", "text": "..." },
    { "type": "code", "text": "...", "language": "python" }
  ]
}
```

响应: `{ "success": true, "data": { "filename": "export_1718000000.pptx" } }`

### 4.7 下载 PPTX

```
GET /api/resources/download-pptx?filename=export_1718000000.pptx
Authorization: Bearer {token}
```

返回 PPTX 文件流（`Content-Type: application/vnd.openxmlformats-officedocument.presentationml.presentation`）。

### 4.8 导出 PDF

```
POST /api/resources/export-pdf
Content-Type: application/json
Authorization: Bearer {token}
```

请求体同 4.6，响应: `{ "success": true, "data": { "filename": "export_1718000000.pdf" } }`

### 4.9 下载 PDF

```
GET /api/resources/download-pdf?filename=export_1718000000.pdf
Authorization: Bearer {token}
```

返回 PDF 文件流。

---

## 5. 习题模块 `/api/exercise`

### 5.1 生成习题 (SSE 流式)

```
POST /api/exercise/generate
Content-Type: application/json
Authorization: Bearer {token}
```

请求体:
```json
{
  "topic": "Python 列表推导式",
  "knowledge_node_id": "python_list_comprehension",
  "strategy": "weakness",
  "count": 5,
  "difficulty": "medium"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| topic | String | 否 | 知识点（与 knowledge_node_id 二选一，后者优先） |
| knowledge_node_id | String | 否 | 知识图谱节点ID（优先） |
| strategy | String | 否 | `weakness`(薄弱点)/`review`(错题同类)/`new`(新题) |
| count | int | 否 | 题目数量，默认 3，范围 1-20 |
| difficulty | String | 否 | `easy`/`medium`/`hard`，默认 medium |

SSE 流式返回（`progress` → `done`），完成后习题自动入库。

### 5.2 批改习题

```
POST /api/exercise/grade
Content-Type: application/json
Authorization: Bearer {token}
```

请求体:
```json
{
  "type": "choice",
  "user_answer": "B",
  "correct_answer": "B",
  "choices": ["A.xxx", "B.yyy", "C.zzz", "D.www"],
  "points": 5,
  "resource_id": 1
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| type | String | 是 | 题型: `choice`/`multi`/`fill`/`code`/`essay` |
| user_answer | String | 是 | 用户答案 |
| correct_answer | String | 否 | 正确答案(客观题必填) |
| choices | Array | 否 | 选项列表 |
| multi | Boolean | 否 | 是否多选 |
| points | int | 否 | 分值 |
| reference_answer | String | 否 | 参考答案(主观题) |
| rubric | String | 否 | 评分标准 |
| resource_id | Long | 否 | 关联资源 ID,传入后自动记录成绩 |

响应(包含 AI 评分和解析):
```json
{
  "code": 0,
  "data": {
    "correct": true,
    "score": 5,
    "maxScore": 5,
    "explanation": "...",
    "hint": "..."
  }
}
```

### 5.3 评估报告

```
POST /api/exercise/report
Content-Type: application/json
Authorization: Bearer {token}
```

请求体:
```json
{
  "evaluation_results": {
    "python_basics": { "score": 80, "total": 100 },
    "list_comprehension": { "score": 60, "total": 100 }
  }
}
```

### 5.4 错题分析

```
POST /api/exercise/error-analysis
Content-Type: application/json
Authorization: Bearer {token}
```

请求体:
```json
{
  "errors": [
    { "question": "什么是梯度消失？", "user_answer": "不知道", "correct_answer": "..." }
  ],
  "level": 1
}
```

返回逐题错误原因分析 + 改进建议 + 关联知识节点。

### 5.5 练习题分类

```
POST /api/exercise/categorize
Content-Type: application/json
Authorization: Bearer {token}
```

将练习题匹配到知识图谱节点（LLM 分类兜底）。

请求体:
```json
{
  "exercises": [{ "question": "什么是反向传播？", "question_type": "short_answer" }],
  "knowledge_nodes": [{ "id": "backprop", "name": "反向传播" }],
  "course_id": "ai_intro"
}
```

### 5.6 练习会话分析

```
POST /api/exercise/session/analyze
Content-Type: application/json
Authorization: Bearer {token}
```

请求体:
```json
{
  "records": [{ "question": "...", "user_answer": "B", "correct_answer": "B" }],
  "course_id": "ai_intro"
}
```

返回逐知识点报告 + 掌握度更新建议。

### 5.7 练习仪表盘

```
POST /api/exercise/dashboard
Content-Type: application/json
Authorization: Bearer {token}
```

请求体:
```json
{
  "recent_records": [...],
  "course_id": "ai_intro"
}
```

返回练习统计 + 薄弱/强项节点 + 推荐练习节点。

### 5.8 画像增强

```
POST /api/exercise/profile/enrich
Content-Type: application/json
Authorization: Bearer {token}
```

练习数据反哺学生画像。请求体:
```json
{
  "recent_records": [...],
  "session_analysis": {...}
}
```

---

## 6. 画像模块 `/api/profile`

### 6.1 画像对话 (SSE 流式)

```
POST /api/profile/chat
Content-Type: application/json
Authorization: Bearer {token}
```

请求体:
```json
{
  "messages": [
    { "role": "user", "content": "我学过 Python 基础" },
    { "role": "assistant", "content": "好的,了解..." }
  ]
}
```

每次请求传完整的对话历史。返回 SSE 流,对话结束后画像自动更新入库。

### 6.2 画像完整度

```
GET /api/profile/status
Authorization: Bearer {token}
```

响应:
```json
{
  "code": 0,
  "data": {
    "profile_completeness": 0.75,
    "missing_fields": ["learning_goal", "cognitive_style"]
  }
}
```

### 6.3 获取用户画像

```
GET /api/profile/{userId}
Authorization: Bearer {token}
```

---

## 6.5 解题 `/api/solve`

```
POST /api/solve
Content-Type: application/json
Authorization: Bearer {token}
```

分步解答数学/科学/逻辑问题（SSE流式）。

请求体:
```json
{
  "question": "推导反向传播中权重更新的链式法则",
  "context": ""
}
```

SSE事件: `steps`(解题步骤) → `token`(逐字详解) → `confidence`(置信度) → `done`

---

## 7. 知识图谱 `/api/knowledge-graph`

### 7.1 获取课程知识图谱

```
GET /api/knowledge-graph/{courseId}?userId={userId}
Authorization: Bearer {token}
```

courseId 示例: `ai_intro`, `python_basics`

响应含节点（含 `status`/`mastery`/`color` 对象）和边（`depends_on`/`unlocks`）。

### 7.2 节点详情卡片

```
GET /api/knowledge-graph/{courseId}/node/{nodeId}?userId={userId}&totalExercises=10&lastPracticed=2025-06-10
Authorization: Bearer {token}
```

返回节点信息、前置/后置依赖、子概念掌握度、推荐动作按钮。

### 7.3 节点掌握度分布

```
GET /api/knowledge-graph/masteries/{courseId}?userId={userId}
Authorization: Bearer {token}
```

---

## 7A. 图谱操作 `/api/graph`

以下接口全部 POST，Java 从 DB 读取数据后传入 Python。

| 接口 | 说明 | 关键字段 |
|------|------|---------|
| `POST /api/graph/extract` | 从对话中提取知识节点 | `user_message`, `assistant_reply` |
| `POST /api/graph/nodes` | 批量更新节点/边 | `updates: [{action, data}]` |
| `POST /api/graph/masteries` | 批量更新掌握度 | `events: [{node_id, event_type, score}]` |
| `POST /api/graph/next-node` | 推荐下一学习节点 | `course_id` |
| `POST /api/graph/progress` | 学习进度概要 | `course_id` |
| `POST /api/graph/check-prerequisites` | 前置条件检查 | `node_id`, `threshold` |
| `POST /api/graph/export-mermaid` | 导出 Mermaid 语法 | `course_id` |
| `POST /api/graph/layered` | 带层级信息图谱 | `course_id` |

---

## 8. 节点掌握度 `/api/node-masteries`

### 8.1 获取用户课程所有掌握度

```
GET /api/node-masteries?userId={userId}&courseId={courseId}
Authorization: Bearer {token}
```

### 8.2 获取单个节点掌握度

```
GET /api/node-masteries/{nodeId}?userId={userId}
Authorization: Bearer {token}
```

### 8.3 更新掌握度

```
PUT /api/node-masteries/{nodeId}
Content-Type: application/json
Authorization: Bearer {token}
```

请求体:
```json
{
  "user_id": 1,
  "course_id": "ai_intro",
  "mastery": 0.85,
  "review_count": 3
}
```

### 8.4 掌握度分布统计

```
GET /api/node-masteries/distribution?userId={userId}&courseId={courseId}
Authorization: Bearer {token}
```

---

## 9. 学习计划 `/api/plans`

### 9.1 创建计划(含步骤)

```
POST /api/plans
Content-Type: application/json
Authorization: Bearer {token}
```

请求体:
```json
{
  "user_id": 1,
  "course_id": "ai_intro",
  "title": "机器学习入门计划",
  "steps": [
    { "node_id": "ml_01", "topic": "监督学习概述", "order": 1, "node_type": "learn" },
    { "node_id": "ml_01", "topic": "监督学习练习", "order": 2, "node_type": "practice" },
    { "node_id": "ml_02", "topic": "线性回归",   "order": 3, "node_type": "learn" }
  ]
}
```

### 9.2 获取计划详情(含步骤)

```
GET /api/plans/{id}?userId={userId}
Authorization: Bearer {token}
```

### 9.3 更新计划

```
PUT /api/plans/{id}
Content-Type: application/json
Authorization: Bearer {token}
```

请求体:
```json
{ "title": "新标题", "status": "completed" }
```

status: `in_progress` / `completed` / `paused`

### 9.4 获取计划步骤列表

```
GET /api/plans/{planId}/steps
Authorization: Bearer {token}
```

### 9.5 添加步骤

```
POST /api/plans/{planId}/steps
Content-Type: application/json
Authorization: Bearer {token}
```

请求体:
```json
{
  "node_id": "ml_03",
  "topic": "决策树",
  "order": 4,
  "node_type": "learn",
  "depth": 1
}
```

### 9.6 步骤排序位移

```
POST /api/plans/{planId}/steps/shift
Content-Type: application/json
Authorization: Bearer {token}
```

请求体:
```json
{ "after_order": 2 }
```

将步骤插入到 order=2 之后。

### 9.7 锁定后继节点

```
POST /api/plans/{planId}/steps/lock-successors
Content-Type: application/json
Authorization: Bearer {token}
```

请求体:
```json
{ "node_id": "ml_01" }
```

锁定 ml_01 的所有后继步骤(depends_on 关系的下游节点),状态改为 `locked`。

### 9.8 节点状态变更(原子操作)

```
POST /api/plans/node-status-change
Content-Type: application/json
Authorization: Bearer {token}
```

请求体:
```json
{
  "user_id": 1,
  "node_id": "ml_01",
  "new_status": "completed",
  "plan_id": 1
}
```

自动: 锁定后继节点 + 插入复习步骤 + 更新计划进度计数。

### 9.9 更新单个步骤

```
PUT /api/plan-steps/{stepId}
Content-Type: application/json
Authorization: Bearer {token}
```

请求体:
```json
{ "status": "completed", "order": 1 }
```

step status: `pending` / `in_progress` / `completed` / `locked`

### 9.10 查询计划状态（软着陆检测）

```
GET /api/plans/{planId}/status?userId={userId}
Authorization: Bearer {token}
```

返回含 `soft_landing` 字段：`continue`(直接继续) / `warmup`(出热身题) / `regression_check`(走回归检测)。

### 9.11 今日任务

```
GET /api/plans/{planId}/today?userId={userId}
Authorization: Bearer {token}
```

返回当日应完成步骤 + 资源建议。

### 9.12 更新步骤进度

```
POST /api/plans/{planId}/progress
Content-Type: application/json
Authorization: Bearer {token}
```

请求体:
```json
{
  "step_id": 10, "step_order": 4,
  "status": "completed", "activity_type": "exercise",
  "score": 0.85, "duration_minutes": 25
}
```

### 9.13 回归检测（两阶段）

```
POST /api/plans/{planId}/regression-check
Content-Type: application/json
Authorization: Bearer {token}
```

阶段1（不传 answers）出检测题 → 阶段2（传 answers）判分+重排计划。

### 9.14 复习日程

```
GET /api/plans/{planId}/review-schedule?userId={userId}&daysAhead=7
Authorization: Bearer {token}
```

返回未来 N 天间隔重复复习安排。

### 9.15 步骤完成巩固

```
POST /api/plans/{planId}/complete-step
Content-Type: application/json
Authorization: Bearer {token}
```

完成学习步骤后生成巩固练习题。

---

## 10. 学习记录 `/api/record`

### 10.1 我的学习记录

```
GET /api/record/list
Authorization: Bearer {token}
```

### 10.2 按类型筛选记录

```
GET /api/record/list/{type}
Authorization: Bearer {token}
```

type: `course_doc`, `mind_map`, `exercise`, `reading`, `code_practice`

### 10.3 某资源的记录

```
GET /api/record/resource/{resourceId}
Authorization: Bearer {token}
```

响应:
```json
{
  "code": 0,
  "data": {
    "id": 1,
    "userId": 1,
    "resourceId": 1,
    "progress": 100,
    "score": 85,
    "timeSpent": 1200,
    "createdAt": "2025-06-12 10:30:00"
  }
}
```

| 字段 | 说明 |
|------|------|
| progress | 进度 0-100 |
| score | 得分 |
| timeSpent | 学习时长(秒) |

### 10.4 学习统计

```
GET /api/record/stats
Authorization: Bearer {token}
```

响应:
```json
{
  "code": 0,
  "data": {
    "totalScore": 850,
    "averageScore": 72.5,
    "totalRecords": 12
  }
}
```

---

## 11. 学习活动 `/api/learning-activities`

### 11.1 记录学习活动

```
POST /api/learning-activities
Content-Type: application/json
Authorization: Bearer {token}
```

请求体:
```json
{
  "user_id": 1,
  "plan_id": 1,
  "step_id": 5,
  "activity_type": "exercise",
  "duration_minutes": 30,
  "score": 0.85
}
```

activity_type: `exercise` / `review` / `study`

### 11.2 最近活动列表

```
GET /api/learning-activities?userId={userId}&limit=20
Authorization: Bearer {token}
```

### 11.3 活动统计

```
GET /api/learning-activities/stats?userId={userId}
Authorization: Bearer {token}
```

### 11.4 得分趋势

```
GET /api/learning-activities/score-trend?userId={userId}&days=30
Authorization: Bearer {token}
```

响应:
```json
{
  "code": 0,
  "data": [
    { "date": "2025-06-01", "score": 0.72 },
    { "date": "2025-06-02", "score": 0.80 }
  ]
}
```

### 11.5 习题计数

```
GET /api/learning-activities/count-exercises?userId={userId}
Authorization: Bearer {token}
```

---

## 12. 学习路径 `/api/path`

### 12.1 获取学习路径

```
GET /api/path/{userId}
Authorization: Bearer {token}
```

返回 AI 为用户规划的学习路径(由 Python 端生成)。

---

## 13. 文件上传 `/api/file`

### 13.1 上传文件（含图片，用于聊天多模态）

```
POST /api/file/upload
Content-Type: multipart/form-data
Authorization: Bearer {token}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | File | 是 | 任意文件 |

响应:
```json
{
  "code": 0,
  "data": {
    "fileId": 1,
    "url": "http://localhost:9000/learning-resources/images/uuid.png?sign=...",
    "fileName": "images/uuid.png",
    "originalName": "我的截图.png"
  }
}
```

**图片用于聊天对话的流程：**
```
1. POST /api/file/upload (multipart) → 拿到 url 字段
2. POST /api/chat { "message": "...", "images": [url] }
   → Java 自动将 MinIO URL 转 base64 data URI
   → Python 多模态 LLM 分析图片
```

> Java 在转发给 Python 前会自动下载 MinIO 图片并转为 base64 data URI，避免 Python SSRF 防护拦截 localhost URL。

### 13.2 获取文件访问 URL

```
GET /api/file/url/{fileId}
Authorization: Bearer {token}
```

响应:
```json
{
  "code": 0,
  "data": "http://localhost:9000/learning-resources/xxx.png?X-Amz-..."
}
```

返回 MinIO 预签名 URL,有效期 7 天,可直接用于 `<img src>` 或下载。

### 13.3 删除文件

```
DELETE /api/file/{fileId}
Authorization: Bearer {token}
```

---

## 14. 典型前端交互流程

### 14.1 新用户引导流程

```
注册 → 登录(获取token) → 初始画像对话(POST /api/profile/chat SSE)
→ 获取学习路径(GET /api/path/{userId})
→ 创建学习计划(POST /api/plans)
→ 查看今日任务(GET /api/plans/{id}/today)
→ 开始学习
```

### 14.2 日常学习流程

```
选择计划 → 查看计划状态(GET /api/plans/{id}/status) 处理软着陆
→ 查看今日任务(GET /api/plans/{id}/today)
→ 进入学习 → 统一对话(POST /api/chat SSE)
→ AI 自动生成资源/习题/答疑
→ 做题(POST /api/exercise/generate SSE → POST /api/exercise/grade)
→ 完成步骤(POST /api/plans/{id}/progress)
→ 完成巩固(POST /api/plans/{id}/complete-step)
→ 查看记录(GET /api/record/list)
```

### 14.3 自由探索流程

```
统一对话(POST /api/chat, mode=auto) → AI 自动判断意图
→ 生成路径/资源/习题/解题
→ 资源自动入库 → 查看我的资源(GET /api/resources/list)
→ 查看知识图谱(GET /api/knowledge-graph/{courseId})
→ 图谱节点操作(POST /api/graph/next-node, progress 等)
```

---

## 15. 错误处理

### 15.1 HTTP 状态码

| 状态码 | 含义 |
|--------|------|
| 200 | 正常 |
| 400 | 业务错误,看 message |
| 401 | 未登录,跳转登录页 |
| 500 | 服务器内部错误 |

### 15.2 401 未登录

```json
{ "error": "请先登录" }
```

前端拦截器:收到 401 时清除本地 token 并跳转登录页。

### 15.3 业务错误

```json
{ "code": 400, "message": "手机号已注册", "data": null }
```

前端应统一判断 `code !== 0` 时用 Toast/Message 展示 `message`。

---

## 16. 前端接入 Checklist

- [ ] 封装 HTTP 请求，自动携带 `Authorization` Header
- [ ] 实现 401 响应拦截，跳转登录页
- [ ] 封装 SSE 消费工具（fetch + ReadableStream，POST 不能用 EventSource）
- [ ] SSE 接口设置 120 秒超时
- [ ] 登录/注册页
- [ ] 主对话页（流式 SSE token 展示 + markdown 渲染）
- [ ] 对话历史侧栏（会话列表 + 消息历史）
- [ ] `/api/chat` 万能入口，mode=auto，不自己判断用户意图
- [ ] 答疑保存并回传 `conversation_id`
- [ ] 资源列表页 + 资源详情页（JSON 内容渲染）
- [ ] 资源生成进度条绑定 `progress` 字段
- [ ] 资源工坊支持 7 种 block.type：section/code/callout/mindmap/mermaid/flash_cards/project
- [ ] PPTX/PDF 导出下载
- [ ] 习题页（生成 → 展示 → 作答 → AI 批改）
- [ ] 错题分析 + 会话分析
- [ ] 学习计划页（计划列表 → 步骤树 → 软着陆回归检测 → 今日任务）
- [ ] 知识图谱页（节点+边可视化，直接用 `color` 对象渲染，点击节点看详情卡片）
- [ ] 节点详情卡片 `actions` 按 type 渲染按钮（primary/secondary/warning）
- [ ] 学习记录/统计页（成绩趋势图）
- [ ] 练习仪表盘
- [ ] 画像构建页（引导式对话，区分 active/tentative 条目）
- [ ] `recommendation` 事件处理 — 收到后渲染「去练习」按钮
- [ ] 所有接口错误兜底（网络超时 + AI 服务不可用 502）
