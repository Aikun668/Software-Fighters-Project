# AI 服务接口契约

> 版本: v1.0 | 维护: AI Agent 组 | 基址: `http://127.0.0.1:8001/internal`

---

## 快速导航

| # | 端点 | 方式 | 用途 |
|---|------|------|------|
| 1 | `/profile/chat` | POST (SSE) | 画像构建对话 |
| 2 | `/profile/workflow/status` | GET | 画像完整度查询 |
| 3 | `/path/{student_id}` | GET | 学习路径规划 |
| 4 | `/resources/generate` | POST (SSE) | 学习资源生成 |
| 5 | `/tutor/chat` | POST (SSE) | 智能辅导答疑 |
| 6 | `/exercise/generate` | POST (SSE) | 练习题生成 |

---

## 后端 → AI 服务（你们传我们的，公共字段）

### user_id

| 字段 | 说明 |
|------|------|
| 类型 | `int` |
| 来源 | 后端从登录态/JWT 解析 |
| 用途 | 查画像、关联持久化内容 |

### student_profile（可选）

| 字段 | 说明 |
|------|------|
| 类型 | `object` |
| 来源 | 后端从 DB 查 `student_profiles` 表 |
| 用途 | 个性化生成（内容难度、解释风格） |

六维度字段：

| 维度 | 类型 | 说明 |
|------|------|------|
| `knowledge_base` | `int` | 知识水平 0-100 |
| `cognitive_style` | `string \| null` | 学习风格 (visual/verbal/logical 等) |
| `learning_goal` | `string \| null` | 学习目标 |
| `weak_points` | `string[]` | 薄弱知识点列表 |
| `learning_pace` | `string \| null` | 学习节奏 (fast/medium/slow) |
| `interest_direction` | `string[]` | 兴趣方向 |

**注意**: `student_profile` 在所有端点中均为可选参数。不传则 AI 服务自行从 DB 查询。

### messages

| 字段 | 说明 |
|------|------|
| 类型 | `[{role: string, content: string}]` |
| 来源 | 前端发给后端，后端原样传递 |
| 用途 | LLM 需要完整多轮对话上下文 |

---

## 一、Agent → 后端（接口详情）

### 1. 画像对话

```
POST /internal/profile/chat
```

**入参**:

```json
{
  "user_id": 1,
  "messages": [
    {"role": "user", "content": "我学过Python，想入门机器学习"}
  ]
}
```

**出参**: SSE 流，事件类型如下（`data:` 前缀，`\n\n` 结尾）：

| 事件 type | payload.content | 触发时机 |
|-----------|----------------|---------|
| `token` | 单个字符 | AI 逐字输出追问 |
| `profile_update` | 画像对象 | 本轮对话提取到新字段 |
| `profile_complete` | `{filled_dimensions: int}` | 6 维中 ≥4 维有值 |
| `done` | 空 | 本轮结束 |

SSE 示例：

```
data: {"type":"token","content":"你"}\n\n
data: {"type":"token","content":"好"}\n\n
data: {"type":"profile_update","content":{"knowledge_base":30,"learning_goal":"入门机器学习"}}\n\n
data: {"type":"done"}\n\n
```

---

### 2. 画像完整度查询

```
GET /internal/profile/workflow/status?user_id=1
```

**入参**: `user_id` (query)

**出参**:

```json
{
  "complete": false,
  "filled_dimensions": 3,
  "total_dimensions": 6,
  "dimensions": ["knowledge_base", "cognitive_style", "learning_goal", "weak_points", "learning_pace", "interest_direction"]
}
```

---

### 3. 学习路径规划

```
GET /internal/path/{student_id}
```

**入参**: `student_id` (路径参数)

**出参**:

```json
{
  "student_id": "1",
  "steps": [
    {
      "title": "反向传播原理",
      "topic": "反向传播",
      "order": 1,
      "status": "pending",
      "resource_id": 101,
      "preview": "反向传播利用链式法则高效计算神经网络中每一层参数的梯度..."
    }
  ],
  "concept_graph": {
    "反向传播": ["梯度下降", "链式法则"],
    "梯度下降": ["损失函数"],
    "链式法则": ["偏导数"]
  },
  "resource_ids": [101, 102, 103],
  "response": "已为您规划 5 步学习路径。"
}
```

**注意**: `resource_id` 初次可能为 `null`，资源生成后由系统回填。

---

### 4. 学习资源生成

```
POST /internal/resources/generate
```

**入参**:

```json
{
  "user_id": 1,
  "topic": "反向传播",
  "student_profile": { ... }
}
```

**出参**: SSE 流

| 事件 type | payload | 触发时机 |
|-----------|---------|---------|
| `progress` | `{stage: "plan", content: "..."}` | 开始分析知识点 |
| `progress` | `{stage: "outline_done", content: "..."}` | 大纲规划完成 |
| `progress` | `{stage: "generating", index: 1, total: 5, block_type: "course_doc"}` | 逐块生成 |
| `content_block` | `{type: "course_doc", heading: "...", content: "..."}` | 课程文档 |
| `content_block` | `{type: "mindmap", ...}` | 思维导图 |
| `content_block` | `{type: "callout", heading: "拓展阅读", content: "..."}` | 拓展阅读 |
| `progress` | `{stage: "exercises", content: "..."}` | 练习题生成完成 |
| `done` | `{content_blocks: [...], questions: [...], resource_ids: [...], response: "..."}` | 全部完成 |

---

### 5. 智能辅导答疑

```
POST /internal/tutor/chat
```

**入参**:

```json
{
  "user_id": 1,
  "messages": [
    {"role": "user", "content": "链式法则不太懂"},
    {"role": "assistant", "content": "链式法则是微积分中..."},
    {"role": "user", "content": "能举个具体例子吗"}
  ],
  "student_profile": { ... }
}
```

**出参**: SSE 流

| 事件 type | payload | 说明 |
|-----------|---------|------|
| `token` | `{content: "单字符"}` | AI 逐字回复 |
| `done` | 空 | 本轮结束 |

---

### 6. 练习题生成

```
POST /internal/exercise/generate
```

**入参**:

```json
{
  "user_id": 1,
  "topic": "反向传播",
  "count": 5,
  "difficulty": "medium",
  "student_profile": { ... }
}
```

| 字段 | 类型 | 约束 |
|------|------|------|
| `count` | `int` | 1-20 |
| `difficulty` | `string` | easy / medium / hard |

**出参**: SSE 流

| 事件 type | payload | 说明 |
|-----------|---------|------|
| `progress` | `{stage: "plan", content: "..."}` | 开始规划 |
| `progress` | `{stage: "generate", content: "..."}` | 生成中 |
| `done` | `{questions: [...]}` | questions 结构见下方 |

**question 结构**:

```json
{
  "type": "choice",
  "question": "反向传播算法的核心数学工具是什么？",
  "options": ["A. 泰勒展开", "B. 链式法则", "C. 傅里叶变换", "D. 主成分分析"],
  "answer": "B",
  "explanation": "反向传播利用链式法则将误差从输出层逐层回传至输入层。"
}
```

---

## 二、错误返回格式（统一）

所有接口在出错时返回 JSON，HTTP 状态码对应错误类型：

```json
{
  "error": "人类可读的错误描述"
}
```

| 状态码 | 含义 |
|--------|------|
| `400` | 参数校验失败（缺少必填字段、格式错误） |
| `500` | AI 服务内部异常（LLM 超时、DB 故障等） |

**示例**:

```
HTTP 400
{"error": "topic is required"}

HTTP 400
{"error": "count must be an integer between 1 and 20"}

HTTP 500
{"error": "LLM call failed: Spark WebSocket timeout"}
```

---

## 三、运行环境

| 项 | 值 |
|----|-----|
| 基址 | `http://127.0.0.1:8001` |
| LLM 提供者 | 讯飞星火 (WebSocket) / OpenAI 兼容 (HTTP)，通过 `LLM_PROVIDER` 环境变量切换 |
| Mock 模式 | `USE_MOCK_LLM=true` 时使用内置 mock 回复，不走真实 LLM |
| 向量库 | ChromaDB (BGE-small-zh-v1.5, 512维)，10 份知识文档，93 个向量块 |
| 数据库 | MySQL (计划迁移 SQLite) |
| 健康检查 | `GET /health` → `{"status":"ok","db":"connected"}` |
| 调用超时 | 建议 ≥ 120 秒（单次 LLM 生成最长耗时） |

---

## 四、完整调用链路（供参考）

```
学生首次进入
  ↓
前端调 GET /profile/workflow/status
  → 画像不完整
  ↓
前端发起画像对话 POST /profile/chat
  → 多轮追问 → 画像完整
  ↓
前端调 GET /path/{student_id}
  → 拿到学习路径 steps
  ↓
对路径中每个 step：
  ├─ POST /resources/generate  → 获取课程资料
  ├─ POST /exercise/generate   → 获取配套练习
  └─ 学习中 POST /tutor/chat   → 随时答疑
```
