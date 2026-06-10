# Java → Python AI 服务 API 对接文档

> **架构**：Architecture #2 — Java 调 Python 做 AI 推理，Java 负责全部数据 CRUD
> **端口**：Python AI 服务运行在 `http://localhost:8001`
> **路由前缀**：所有 AI 端点统一在 `/internal/*` 下
> **原则**：Python 绝不调 Java，Java 把全部上下文放在请求体中传入
> **最后更新**：2026-06-09

---

## 核心约定

1. **请求方向**：Java → Python（单向调用）
2. **数据传递**：Java 在请求体（JSON）中传入所有需要的数据（画像、消息历史、plan 步骤等）
3. **响应格式**：
   - 非流式：`{"success": true, "data": {...}}` 或 `{"success": false, "errorCode": "...", "error": "..."}`
   - 流式：SSE（`text/event-stream`），每个事件格式 `data: {"type": "...", ...}\n\n`
4. **Python 不做持久化**：所有结果在响应中返回，Java 自行持久化
5. **Python 不调 Java**：Python 服务无任何 Java HTTP 调用

---

## SSE 事件格式

所有流式端点（SSE）统一使用以下事件类型：

| type | 说明 | 示例 |
|------|------|------|
| `token` | 逐字输出 | `{"type": "token", "content": "你好"}` |
| `progress` | 进度提示 | `{"type": "progress", "stage": "plan", "content": "正在规划..."}` |
| `stage_start` | 阶段开始 | `{"type": "stage_start", "stage": "content", "message": "正在生成..."}` |
| `stage_end` | 阶段结束 | `{"type": "stage_end", "stage": "content", "message": "完成"}` |
| `error` | 错误事件 | `{"type": "error", "content": "生成失败"}` |
| `profile_update` | 画像更新 | `{"type": "profile_update", "content": {...}}` |
| `meta` | 元信息 | `{"type": "meta", "conversation_id": 42}` |
| `done` | **流结束（含完整结果）** | 见下方 done event 格式 |

### done event 格式（标准化）

所有 SSE 端点统一在 `done` 事件中包含完整结果：

```json
{
  "type": "done",
  "content_blocks": [...],
  "questions": [...],
  "steps": [...],
  "response": "完整 AI 回复文本",
  "profile_delta": {...},
  "conversation_id": 42,
  "error": null
}
```

Java 从 `done` 事件中提取所需字段并持久化。

---

## 端点清单

### 保留并修改的端点（19 个）

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | POST | `/internal/profile/chat` | 画像对话（SSE） |
| 2 | POST | `/internal/resources/generate` | 资源生成（SSE） |
| 3 | POST | `/internal/tutor/chat` | 导师答疑（SSE） |
| 4 | POST | `/internal/exercise/generate` | 练习题生成（SSE） |
| 5 | POST | `/internal/path/{student_id}` | 学习路径规划 |
| 6 | POST | `/internal/profile/workflow/status` | 画像完整度查询 |
| 7 | POST | `/internal/resources/export-pptx` | 导出 PPTX |
| 8 | GET | `/internal/resources/download-pptx` | 下载 PPTX |
| 9 | POST | `/internal/solve` | 解题（SSE） |
| 10 | POST | `/internal/exercise/error-analysis` | 错题分析 |
| 11 | POST | `/internal/exercise/grade` | 批改打分 |
| 12 | POST | `/internal/evaluation/report` | 评估报告生成 |
| 13 | POST | `/internal/knowledge-graph/{course_id}` | 知识图谱 |
| 14 | POST | `/internal/knowledge-graph/{course_id}/node/{node_id}` | 节点卡片 |
| 15 | POST | `/internal/plans/create-from-path` | 一键生成学习路径 |
| 16 | POST | `/internal/plans/{plan_id}/status` | 计划状态+软着陆检测 |
| 17 | POST | `/internal/plans/{plan_id}/regression-check` | 回归检测 |
| 18 | POST | `/internal/plans/{plan_id}/review-schedule` | 复习日程 |
| 19 | POST | `/internal/api/chat` | 统一对话入口（SSE） |
| 20 | POST | `/internal/inquiry/resolve` | 追问解析+资源生成（SSE） |
| 21 | POST | `/internal/conversations/{conversation_id}/summary` | 对话总结 |

### 已删除的端点（7 个，Java 需自行处理）

| # | 方法 | 路径 | 原功能 | Java 替代方案 |
|---|------|------|--------|-------------|
| 1 | POST | `/internal/plans/create` | 创建计划 | Java 直接 INSERT |
| 2 | POST | `/internal/plans/{id}/progress` | 更新进度 | Java UPDATE + 内置 mastery 公式 |
| 3 | POST | `/internal/plans/{id}/resume` | 恢复计划 | Java UPDATE status |
| 4 | POST | `/internal/plans/{id}/node-status-change` | 节点状态联动 | Java UPDATE + 调 /status 重排 |
| 5 | GET | `/internal/user/dashboard` | 仪表盘 | Java 查自己的 DB |
| 6 | POST | `/internal/conversations/{id}/end` | 结束会话 | Java 自己处理 |
| 7 | （原 POST /internal/plans/create 已删） | | | |

---

## 各端点详细说明

### 1. POST /internal/profile/chat

**请求体**：
```json
{
  "messages": [{"role": "user", "content": "我想学AI"}, ...],
  "user_id": 1,
  "student_profile": {                        // ← 新增：Java 传入
    "knowledge_base": 50,
    "cognitive_style": "视觉型",
    "learning_goal": "转行AI工程师",
    "weak_points": ["数学基础"],
    "learning_pace": "中等",
    "interest_direction": ["NLP"],
    "entries": {...},
    "tag_weights": {...},
    "stability_counter": {...},
    "last_extracted_msg_index": 0
  }
}
```

**响应**：SSE 流，done event 含 `profile_delta`（变更后的画像）。

---

### 2. POST /internal/resources/generate

**请求体**：
```json
{
  "topic": "Transformer 架构",
  "user_id": 1,
  "student_profile": {...}
}
```

**响应**：SSE 流，done event 含 `content_blocks` + `questions`。
Java 从 done event 提取结果自行持久化为 Resource。

---

### 3. POST /internal/tutor/chat

**请求体**（简化，不再区分新旧 API）：
```json
{
  "user_id": 1,
  "student_profile": {...},
  "messages": [                              // ← Java 传入完整历史消息
    {"role": "user", "content": "什么是反向传播？"},
    ...
  ]
}
```

**响应**：SSE 流，done event 含 `profile_delta`（后台画像提取结果）。

---

### 4. POST /internal/exercise/generate

**请求体**：
```json
{
  "topic": "反向传播",
  "count": 5,
  "difficulty": "medium",
  "student_profile": {...},
  "user_id": 1
}
```

**响应**：SSE 流，done event 含 `questions`。

---

### 5. POST /internal/path/{student_id}

**请求体**：
```json
{
  "user_id": 1,
  "student_profile": {...}
}
```

**响应**：
```json
{
  "success": true,
  "data": {
    "user_id": 1,
    "steps": [{"topic": "...", "preview": "...", ...}],
    "concept_graph": {...},
    "response": "已为您规划 N 步学习路径"
  }
}
```

---

### 6. POST /internal/profile/workflow/status

**请求体**：
```json
{
  "user_id": 1,
  "student_profile": {...}
}
```

**响应**：画像完整度分析。

---

### 7-8. PPTX 导出/下载

不变。

---

### 9. POST /internal/solve

不变。请求体 `{"question": "...", "context": "...", "user_id": 1}`，SSE 流式返回解题步骤。

---

### 10. POST /internal/exercise/error-analysis

不变。请求体 `{"errors": [...], "level": 1}`，返回分析结果。

---

### 11. POST /internal/exercise/grade

不变。选择题/简答题批改评分。

---

### 12. POST /internal/evaluation/report

**请求体**（移除 user_id，不再触发画像更新）：
```json
{
  "evaluation_results": {
    "results": [...],
    "overall_score": 85,
    "weak_modules": ["math"]
  }
}
```

**响应**：结构化评估报告。Java 自行决定是否更新画像。

---

### 13. POST /internal/knowledge-graph/{course_id}

**请求体**（Java 传入掌握度数据）：
```json
{
  "masteries": {
    "ai_overview": 0.8,
    "ml_basics": 0.5,
    "dl_basics": 0.0
  }
}
```

**响应**：完整知识图谱 JSON（含颜色映射）。

---

### 14. POST /internal/knowledge-graph/{course_id}/node/{node_id}

**请求体**：
```json
{
  "masteries": {"ai_overview": 0.8, ...},
  "total_exercises": 25,
  "last_practiced": "2026-06-08T10:30:00Z"
}
```

**响应**：节点卡片详情。

---

### 15. POST /internal/plans/create-from-path

**请求体**：
```json
{
  "user_id": 1,
  "course_id": "ai_intro",
  "student_profile": {...}
}
```

**响应**（不再调 Java 创建 plan）：
```json
{
  "success": true,
  "data": {
    "course_id": "ai_intro",
    "total_steps": 8,
    "steps": [
      {"step_order": 1, "topic": "AI概述", "knowledge_node_id": "ai_overview", "estimated_days": 1, ...}
    ],
    "concept_graph": {...},
    "summary": "已为您规划8步学习路径"
  }
}
```

Java 自行将 steps 持久化为 Plan。

---

### 16. POST /internal/plans/{plan_id}/status

**请求体**（Java 传入 plan + steps 数据）：
```json
{
  "plan": {
    "id": 42,
    "user_id": 1,
    "status": "paused",
    "total_steps": 10,
    "completed_steps": 3,
    "last_activity_at": "2026-06-01T10:00:00Z"
  },
  "steps": [
    {
      "id": 100, "step_order": 1, "topic": "AI概述",
      "knowledge_node_id": "ai_overview", "status": "completed",
      "topic_difficulty": 3, "mastery_current": 0.85, "review_count": 2
    },
    ...
  ]
}
```

**响应**：含 `soft_landing`（软着陆策略）、`days_idle`、每个 step 的 `decayed_mastery`。

---

### 17. POST /internal/plans/{plan_id}/regression-check

**阶段 1 — 出题**（无 answers）：
```json
// 请求
{
  "user_id": 1,
  "plan": {...},
  "steps": [...],
  "days_idle": 10,
  "answers": null
}
// 响应：{ "strategy": "warmup", "questions": [...] }
```

**阶段 2 — 判分+重排**（有 answers）：
```json
// 请求
{
  "user_id": 1,
  "plan": {...},
  "steps": [...],
  "days_idle": 10,
  "answers": [
    {"topic": "AI概述", "question_type": "choice", "user_answer": "A", "correct_answer": "A", "choices": ["A","B","C","D"]}
  ]
}
// 响应：{ "strategy": "regression_check", "mastery_updates": {...}, "reordered_steps": [...] }
```

Java 根据 `mastery_updates` 和 `reordered_steps` 自行更新 DB。

---

### 18. POST /internal/plans/{plan_id}/review-schedule

**请求体**：
```json
{
  "steps": [
    {"id": 100, "status": "completed", "topic": "AI概述", "topic_difficulty": 3,
     "review_count": 1, "mastery_current": 0.85, "last_review_at": "2026-06-01T10:00:00Z",
     "knowledge_node_id": "ai_overview"}
  ],
  "days_ahead": 7
}
```

**响应**：复习日程列表，含 `urgency` 等级。

---

### 19. POST /internal/api/chat

统一对话入口，双层模式策略。

**请求体**：
```json
{
  "message": "帮我出几道Transformer的题",
  "user_id": 1,
  "mode": "auto",
  "conversation_id": 42,
  "style": "standard",
  "messages": [                               // ← Java 传入历史消息
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！有什么可以帮你的？"}
  ],
  "student_profile": {...}                    // ← Java 传入画像
}
```

**响应**：SSE 流，按 mode 分发到不同子模式。done event 含 `profile_delta` + `conversation_id`。

---

### 20. POST /internal/inquiry/resolve

**请求体**：
```json
{
  "original_message": "我想学AI",
  "answers": ["想做NLP方向", "有Python基础"],
  "user_id": 1,
  "student_profile": {...},
  "questions": [...],
  "suggested_types": ["content", "exercise"],
  "clarified_topic": "NLP入门"
}
```

**响应**：SSE 流，done event 含 `content_blocks` + `questions`。

---

### 21. POST /internal/conversations/{conversation_id}/summary

**请求体**：
```json
{
  "messages": [
    {"role": "user", "content": "什么是反向传播？"},
    {"role": "assistant", "content": "反向传播是..."},
    ...
  ],
  "course_id": "ai_intro"
}
```

**响应**：
```json
{
  "success": true,
  "data": {
    "conversation_id": 42,
    "summary": "本次对话讨论了反向传播算法..."
  }
}
```

---

## Java 需自行实现的功能

以下功能原在 Python 端，现改为 Java 端负责：

| 功能 | 说明 |
|------|------|
| Plan CRUD | 创建/更新/删除计划，更新步骤状态（原 `/plans/create`、`/plans/{id}/progress`、`/plans/{id}/resume`） |
| Node status change | 知识图谱节点状态变化 → 计划重排（原 `/plans/{id}/node-status-change`） |
| Dashboard | 仪表盘数据聚合（原 `/user/dashboard`） |
| Conversation end | 会话结束处理（原 `/conversations/{id}/end`） |
| Profile update | 从 Python 响应中的 `profile_delta` 提取并持久化 |
| Resource persist | 从 Python done event 中的 `content_blocks`/`questions` 提取并持久化 |
| Message save | 从 Python SSE token 流 + done event 拼接完整回复并持久化 |
| Conversation summary | 可调 Python `/conversations/{id}/summary` 获取 LLM 总结后持久化 |

---

## 变更摘要（相对于 Architecture #1）

| 变更类型 | 数量 | 说明 |
|----------|------|------|
| 删除的端点 | 7 | Java 自行处理 |
| GET→POST | 6 | 需传请求体（Java 传入数据） |
| 签名变更 | 13 | 请求体增加字段（profile, messages, steps 等） |
| 移除的依赖 | 6 | java_api_client, conversation_service, profile_service, dashboard_service, summary_service, evaluation_report |
| 新增工具模块 | 1 | `app/utils/conversation_compress.py`（LLM 摘要压缩，供 Java 按需调用） |
