# API 接口契约文档（v1.0）

## 一、文档目的

本文档定义 Java 后端 ↔ Python AI 微服务 之间的接口规范。

**谁调用谁**：
```
前端(Vue) → Java后端(:8080) → Python AI(:8001)
               ↓
            MySQL数据库
```

**为什么不是前端直接调 AI？**
- 安全：AI 服务只监听 127.0.0.1，不对外暴露
- 统一：前端只认 Java 后端的 API，后端做转发和认证
- 数据：后端需要记录调用日志、限流、计费

---

## 二、你需要告诉我的信息（后端 → AI）

### 2.1 User 表结构（必须）

**为什么**：`student_profiles` 表的 `user_id` 是外键，关联 `users.id`。如果字段对不上，画像存不进去。

请后端提供：
```sql
-- 你的 User 表实际建表语句
CREATE TABLE users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,  -- 还是 Integer？
    student_id VARCHAR(20) UNIQUE,         -- 学号
    username VARCHAR(50) UNIQUE,
    ...
);
```

**关键确认点**：
| 字段 | 我方假设 | 需要确认 |
|------|----------|----------|
| 主键类型 | `Integer` | 你用的是 `Integer` 还是 `Long/BIGINT`？ |
| 学号字段 | `student_id` (String) | 你的字段名是什么？ |
| 密码存储 | `password_hash` | 你用的字段名和加密方式？ |

**我方当前的 User 模型**：
```python
class User(Base):
    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String(20), unique=True)
    full_name = Column(String(50))
    role = Column(String(20), default="student")
    username = Column(String(50), unique=True)
    email = Column(String(100), unique=True)
    password_hash = Column(String(255))
```

### 2.2 JWT 认证方式（必须）

**为什么**：AI 服务需要知道请求来自合法的后端，不是外部直接访问。

**当前方案（需确认）**：
- 方案 A：后端调用 AI 时带 JWT Token，AI 服务验证 Token
- 方案 B：内网白名单，AI 只接受来自后端的 IP（127.0.0.1）
- 方案 C：API Key，后端调用时带一个固定 secret

**建议**：先用方案 B（内网白名单），最简单。如果部署到服务器，再加方案 A（JWT）。

**需要你提供**：
```
- JWT Secret（如果用方案 A）
- JWT 算法（默认 HS256）
- Token 放在 Header 的哪个字段（默认 Authorization: Bearer <token>）
```

### 2.3 数据库连接信息（必须）

**为什么**：AI 服务需要读写 MySQL 的 `student_profiles` 表。

**需要你提供**：
```
数据库地址：localhost:3306（还是其他？）
数据库名：ai_edu（还是其他？）
用户名/密码：与 Java 后端共用，还是单独建一个用户？
```

**我方当前的连接配置**：
```
mysql+aiomysql://root:123666@localhost:3306/ai_edu
```

### 2.4 学生画像的数据格式（必须）

**为什么**：后端可能也在存画像，需要确认字段名和类型一致。

**我方当前的画像结构**：
```json
{
    "knowledge_base": 50,           // Integer, 0-100
    "cognitive_style": "visual",    // String
    "learning_goal": "掌握深度学习", // String
    "weak_points": ["数学", "Python"], // List<String>
    "learning_pace": "moderate",    // String: slow/moderate/fast
    "interest_direction": ["CV", "NLP"] // List<String>
}
```

**需要你确认**：
- 这 6 个维度够不够？你有没有额外维度？
- `weak_points` 和 `interest_direction` 你存成 JSON 数组还是单独一张表？
- 有没有`created_at`、`updated_at`时间戳？

---

## 三、你需要告诉后端的信息（AI → 后端）

### 3.1 AI 服务启动方式

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入：
# - SPARK_API_KEY（星火 API）
# - SPARK_API_SECRET
# - DATABASE_URL（MySQL 连接串）
# - USE_MOCK_LLM=false（真实模式）

# 启动
python main.py
# 服务运行在：http://127.0.0.1:8001
```

### 3.2 接口清单（5 个端点）

#### 端点 1：画像构建对话
```
POST http://127.0.0.1:8001/internal/profile/chat
Content-Type: application/json

请求体：
{
    "user_id": 1,                    // Integer，用户的数据库主键 ID
    "messages": [                    // Array，对话历史
        {"role": "user", "content": "我数学基础不好"},
        {"role": "assistant", "content": "没关系，我们可以..."}
    ]
}

响应：SSE 流（text/event-stream）

事件类型：
1. token: {"type": "token", "content": "你"}     // 逐字流式输出
2. token: {"type": "token", "content": "好"}
3. ...
4. profile_update: {"type": "profile_update", "content": {"knowledge_base": 30, "weak_points": ["数学"]}}  // 画像更新
5. profile_complete: {"type": "profile_complete", "filled_dimensions": 6}  // 画像完成（可选）
6. done: {"type": "done"}                       // 流结束

业务逻辑：
- AI 从对话中提取 6 维画像
- 实时更新到 MySQL student_profiles 表
- 流式返回回复文本
```

#### 端点 2：智能答疑（RAG）
```
POST http://127.0.0.1:8001/internal/tutor/chat
Content-Type: application/json

请求体：
{
    "user_id": 1,
    "messages": [
        {"role": "user", "content": "CNN 是什么？"}
    ],
    "student_profile": {             // Optional，不传则从 DB 加载
        "knowledge_base": 50,
        "weak_points": ["数学"]
    }
}

响应：SSE 流

事件类型：
1. token: {"type": "token", "content": "C"}
2. token: {"type": "token", "content": "N"}
3. ...
4. done: {"type": "done"}

业务逻辑：
- AI 先从 ChromaDB 知识库检索相关文档
- 结合学生画像生成个性化回答
- 流式返回（打字机效果）
```

#### 端点 3：资源生成（文档+题目+思维导图）
```
POST http://127.0.0.1:8001/internal/resources/generate
Content-Type: application/json

请求体：
{
    "user_id": 1,
    "topic": "卷积神经网络",           // String，必填，知识点名称
    "student_profile": {              // Optional
        "knowledge_base": 50,
        "weak_points": ["数学"]
    }
}

响应：SSE 流

事件类型：
1. progress: {"type": "progress", "stage": "plan", "content": "正在分析知识点..."}
2. progress: {"type": "progress", "stage": "outline_done", "content": "大纲生成完成..."}
3. progress: {"type": "progress", "stage": "generating", "index": 1, "total": 5, "block_type": "section"}
4. content_block: {"type": "content_block", "data": {"type": "section", "heading": "概述", "content": "CNN 是一种..."}}
5. progress: {"type": "progress", "stage": "generating", "index": 2, "total": 5, "block_type": "code"}
6. content_block: {"type": "content_block", "data": {"type": "code", "heading": "代码示例", "content": "```python\n..."}}
7. ...
8. progress: {"type": "progress", "stage": "exercises", "content": "已生成 3 道练习题"}
9. done: {"type": "done", "content_blocks": [...], "questions": [...], "resource_ids": [], "response": "已生成...", "error": ""}

业务逻辑：
- AI 生成内容大纲
- 按角色（section/code/callout/mindmap）逐块生成
- 同时生成配套练习题
- content_block 是实际内容，前端直接渲染
```

#### 端点 4：练习题生成
```
POST http://127.0.0.1:8001/internal/exercise/generate
Content-Type: application/json

请求体：
{
    "user_id": 1,
    "topic": "决策树",                // String，必填
    "count": 3,                       // Integer，1-20，题目数量
    "difficulty": "medium",           // String: easy/medium/hard
    "student_profile": {}             // Optional
}

响应：SSE 流

事件类型：
1. progress: {"type": "progress", "stage": "plan", "content": "正在规划..."}
2. progress: {"type": "progress", "stage": "generate", "content": "已生成 3 道题目"}
3. done: {"type": "done", "questions": [
    {
        "question_type": "choice",
        "question": "关于决策树，以下哪项正确？",
        "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
        "correct_answer": "A",
        "explanation": "..."
    }
]}

业务逻辑：
- AI 先规划题型蓝图
- 逐题生成完整题目（题干+选项+答案+解析）
- 根据薄弱点优先出题
```

#### 端点 5：学习路径规划
```
GET http://127.0.0.1:8001/internal/path/{student_id}

// student_id 可以是学号或用户 ID

响应：JSON（非 SSE，一次性返回）

{
    "student_id": "2021001",
    "steps": [
        {"order": 1, "topic": "Python 基础", "status": "pending", "resource_id": null},
        {"order": 2, "topic": "机器学习基础", "status": "recommended", "resource_id": null}
    ],
    "concept_graph": {
        "nodes": [
            {"id": "python", "label": "Python", "description": "...", "weight": 0.3}
        ],
        "edges": [
            {"src": "python", "dst": "ml", "relation": "depends_on", "rationale": "..."}
        ]
    },
    "resource_ids": [],
    "response": "已为您规划 5 步学习路径"
}

业务逻辑：
- AI 根据画像设计学习路径
- 返回步骤列表 + 概念图谱
- 前端可视化展示
```

#### 端点 6：画像完整度查询（新增）
```
GET http://127.0.0.1:8001/internal/profile/workflow/status?user_id=1

响应：JSON
{
    "is_complete": false,
    "filled_dimensions": 3,
    "total_dimensions": 6,
    "missing_dimensions": ["learning_goal", "learning_pace", "interest_direction"],
    "completion_percentage": 50
}

业务逻辑：
- 前端用来判断是否需要继续引导用户完善画像
- 比如只填了 3 个维度，提示"再聊聊你的学习目标"
```

### 3.3 SSE 流式输出说明

**为什么用 SSE 而不是 WebSocket？**
- SSE 更简单：基于 HTTP，自动重连，支持文本流
- 前端用 `EventSource` 一行代码就能接
- 适合"打字机效果"：AI 逐字返回

**前端怎么接？**
```javascript
const eventSource = new EventSource('/api/tutor/chat'); // 后端转发

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'token') {
        // 逐字显示
        appendText(data.content);
    } else if (data.type === 'content_block') {
        // 渲染内容块
        renderBlock(data.data);
    } else if (data.type === 'done') {
        // 流结束
        eventSource.close();
    }
};
```

**Java 后端怎么转发？**
```java
// SpringBoot 示例
@PostMapping("/api/tutor/chat")
public SseEmitter tutorChat(@RequestBody ChatRequest request) {
    SseEmitter emitter = new SseEmitter();
    
    // 转发到 Python AI 服务
    WebClient client = WebClient.create("http://127.0.0.1:8001");
    client.post()
        .uri("/internal/tutor/chat")
        .bodyValue(request)
        .retrieve()
        .bodyToFlux(String.class)
        .subscribe(
            data -> emitter.send(data),
            error -> emitter.completeWithError(error),
            () -> emitter.complete()
        );
    
    return emitter;
}
```

---

## 四、数据库交互逻辑

### 4.1 AI 服务读哪些表？

| 表 | 操作 | 说明 |
|----|------|------|
| `student_profiles` | 读/写 | AI 读取画像、更新画像 |
| `users` | 只读 | 确认用户存在（外键约束） |

### 4.2 AI 服务不碰哪些表？

| 表 | 归属 | 说明 |
|----|------|------|
| `learning_records` | 后端/前端 | 学习记录，AI 不直接操作 |
| `resources` | 后端/前端 | 资源元数据，AI 只生成内容 |

### 4.3 画像更新流程

```
用户对话 → ProfileAgent 提取画像 → MySQL upsert → 后续端点读取
```

**关键点**：
- AI 服务自己会写 `student_profiles` 表（upsert）
- 后端不需要操心画像更新逻辑
- 但后端需要确保 `users` 表有对应记录（外键约束）

---

## 五、环境配置清单

### 5.1 AI 服务需要的环境变量

```bash
# .env 文件
SPARK_APP_ID=xxx
SPARK_API_KEY=xxx
SPARK_API_SECRET=xxx

# 或者 OpenAI 兼容
LLM_PROVIDER=openai
OPENAI_BASE_URL=https://api.siliconflow.cn/v1
OPENAI_API_KEY=sk-xxx
OPENAI_MODEL=Qwen/Qwen3.6-35B-A3B

# 数据库（必须和后端一致）
DATABASE_URL=mysql+aiomysql://root:123666@localhost:3306/ai_edu

# ChromaDB
CHROMA_PERSIST_PATH=./chroma_data
CHROMA_COLLECTION=ai_intro

# Mock 开关
USE_MOCK_LLM=false
```

### 5.2 启动顺序

```
1. 启动 MySQL
2. 启动 Redis（后端用）
3. 启动 Python AI 服务（python main.py）
4. 启动 Java 后端（./mvnw spring-boot:run）
5. 启动前端（pnpm dev）
```

---

## 六、常见问题 FAQ

### Q1：AI 服务挂了怎么办？
**A**：AI 服务有全链路降级：
- LLM 失败 → 返回 mock 内容
- DB 失败 → 画像为空 dict
- 知识库失败 → 检索为空

后端不需要特殊处理，正常转发即可。

### Q2：学生画像存在哪里？
**A**：`student_profiles` 表。AI 服务自己读写。后端可以读，但不要写（避免冲突）。

### Q3：AI 生成的内容怎么持久化？
**A**：当前 AI 服务不存生成内容，只返回给后端。后端如果需要存，自己建表存 `content_blocks` 和 `questions`。

### Q4：前端如何展示思维导图？
**A**：`content_blocks` 里 `type: "mindmap"` 的块，content 是 JSON 字符串。前端用 D3.js 或 ECharts 渲染。

### Q5：如何测试 AI 服务？
**A**：
```bash
cd ai-service
python -m pytest tests/ -v  # 93 个用例
```

---

## 七、待确认清单（后端需要回复）

- [ ] User 表建表语句（确认字段名和类型）
- [ ] JWT Secret 和算法（或确认用内网白名单）
- [ ] MySQL 连接信息（地址、端口、库名、账号）
- [ ] 是否需要 AI 服务也做 JWT 验证？
- [ ] 学生画像是否有额外维度？
- [ ] 后端调用 AI 的 WebClient/RestTemplate 配置

---

**文档版本**：v1.0
**更新日期**：2026-05-28
**维护人**：队长（AI 微服务）
