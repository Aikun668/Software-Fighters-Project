# AI 服务 — 前端对接文档

> **版本**: v2.0 | **日期**: 2026-06-05 | **维护**: AI 服务（Python 内核）
>
> **适用对象**: 前端开发工程师（Vue 3 + Element Plus + Pinia）
>
> **架构链路**: `前端(Vue3) → Java后端(:8080) → Python AI服务(:8001)`
>
> 前端只需调用 Java 后端 API，后端负责转发到 AI 服务。**前端不需要直接调 AI 服务。**

---

## 一、接口总览（17 个端点）

### 1.1 核心业务接口（前端 → 后端 → AI）

| # | 端点 | 方法 | 协议 | 用途 | 优先级 |
|---|------|------|------|------|--------|
| 1 | `/api/profile/chat` | POST | **SSE** | 对话式画像构建 | P0 |
| 2 | `/api/tutor/chat` | POST | **SSE** | 智能答疑（RAG + 多模态） | P0 |
| 3 | `/api/resources/generate` | POST | **SSE** | 生成学习资源（文档+题+思维导图+闪卡） | P0 |
| 4 | `/api/exercise/generate` | POST | **SSE** | 生成练习题 | P0 |
| 5 | `/api/path/{studentId}` | GET | JSON | 学习路径规划 + 概念图谱 | P0 |
| 6 | `/api/profile/status` | GET | JSON | 画像完整度查询 | P0 |
| 7 | `/api/exercise/grade` | POST | JSON | 题目评分（选择题/简答题） | P0 |
| 8 | `/api/exercise/error-analysis` | POST | JSON | 错题深度分析 | P1 |
| 9 | `/api/evaluation/report` | POST | JSON | 学习效果评估报告 | P1 |
| 10 | `/api/solve` | POST | **SSE** | 解题（分步推理 + 置信度） | P1 |
| 11 | `/api/chat` | POST | **SSE** | 统一聊天入口（意图自动识别） | P1 |
| 12 | `/api/resources/export-pptx` | POST | JSON | 导出资源为 PPTX | P2 |
| 13 | `/api/resources/download-pptx` | GET | 文件 | 下载 PPTX 文件 | P2 |

### 1.2 知识图谱 + 计划系统接口（Phase 1-3 新增）

| # | 端点 | 方法 | 协议 | 用途 | 优先级 |
|---|------|------|------|------|--------|
| 14 | `/api/knowledge-graph/{courseId}` | GET | JSON | 获取完整知识图谱（含用户掌握度 + 颜色） | P0 |
| 15 | `/api/knowledge-graph/{courseId}/node/{nodeId}` | GET | JSON | 节点详情卡片（子概念 + 上下文 + 推荐动作） | P0 |
| 16 | `/api/plans/{planId}/status` | GET | JSON | 计划状态 + 软着陆检测 | P0 |
| 17 | `/api/plans/{planId}/progress` | POST | JSON | 更新步骤进度 | P0 |
| 18 | `/api/plans/{planId}/resume` | POST | JSON | 中断后恢复计划 | P1 |
| 19 | `/api/plans/{planId}/regression-check` | POST | JSON | 回归检测（出题 → 判分 → 重排） | P1 |
| 20 | `/api/plans/{planId}/review-schedule` | GET | JSON | 未来 N 天复习日程（间隔重复提醒） | P1 |
| 21 | `/api/plans/{planId}/node-status-change` | POST | JSON | 知识图谱节点状态变化联动 | P1 |
| 22 | `/api/plans/create` | POST | JSON | 创建学习计划 | P0 |

---

## 二、SSE 流式接口详解

### 2.1 通用 SSE 事件格式

所有 SSE 接口的每行数据格式：
```
data: {"type": "<事件类型>", ...其他字段}\n\n
```

**通用事件类型**：

| type | 说明 | 何时发送 |
|------|------|----------|
| `token` | 逐字文本输出 | 流式生成过程中持续发送 |
| `progress` | 进度更新 | 阶段性进展 |
| `meta` | 元信息 | 流开始时（如 `conversation_id`） |
| `error` | 错误 | 发生可恢复错误时 |
| `done` | 流结束 | 完成，携带最终结果 |

### 2.2 画像构建对话 — `/api/profile/chat`

**请求**:
```json
{
  "user_id": 1,
  "messages": [
    {"role": "user", "content": "我数学基础不好，但对AI很感兴趣"},
    {"role": "assistant", "content": "没关系！我们可以从基础开始..."}
  ]
}
```

**SSE 事件**:
| type | 关键字段 | 示例 |
|------|----------|------|
| `token` | `content` (string) | `{"type":"token","content":"你"}` |
| `profile_update` | `content` (object) | `{"type":"profile_update","content":{"knowledge_base":30,"weak_points":["数学"]}}` |
| `profile_complete` | `filled_dimensions` (int) | `{"type":"profile_complete","filled_dimensions":6}` |
| `done` | 无 | `{"type":"done"}` |

**前端处理**:
```javascript
const eventSource = new EventSource('/api/profile/chat'); // 后端转发
eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'token') {
    appendText(data.content); // 逐字显示
  } else if (data.type === 'profile_update') {
    updateProfilePanel(data.content); // 实时更新画像面板
  } else if (data.type === 'profile_complete') {
    showCompletionBanner(data.filled_dimensions); // "画像完成！"
  } else if (data.type === 'done') {
    eventSource.close();
  }
};
```

### 2.3 智能答疑 — `/api/tutor/chat`

**请求（推荐方式 — content + conversation_id）**:
```json
{
  "user_id": 1,
  "content": "CNN中的卷积操作具体是怎么计算的？",
  "conversation_id": 42,
  "images": ["data:image/jpeg;base64,/9j/..."]  // 可选，最多5张
}
```

**请求（兼容方式 — messages 数组）**:
```json
{
  "user_id": 1,
  "messages": [
    {"role": "user", "content": "CNN是什么"},
    {"role": "assistant", "content": "CNN是卷积神经网络..."},
    {"role": "user", "content": "卷积操作具体怎么算？"}
  ]
}
```

**SSE 事件**:
| type | 关键字段 | 说明 |
|------|----------|------|
| `meta` | `conversation_id` (int) | **首次对话返回，前端需保存** |
| `token` | `content` (string) | 逐字输出 |
| `done` | 无 | 本轮结束 |

**前端注意事项**:
- 首次调用不传 `conversation_id`，AI 创建新会话并在 `meta` 事件返回 ID
- 后续调用带上 `conversation_id`，AI 自动管理历史 + 长对话压缩
- 图片仅本轮有效，不会跨轮携带

### 2.4 资源生成 — `/api/resources/generate`

**请求**:
```json
{
  "user_id": 1,
  "topic": "卷积神经网络",
  "student_profile": { "knowledge_base": 50, "weak_points": ["数学"] }
}
```

**SSE 事件**:
| type | 关键字段 | 说明 |
|------|----------|------|
| `stage_start` | `stage`, `message`, `progress` | 阶段开始 |
| `progress` | `stage`, `message`, `progress` (0.0-1.0) | 进度更新 |
| `content_block` | `data` (object) | 内容块（直接渲染） |
| `stage_end` | `stage`, `message`, `progress` | 阶段结束 |
| `error` | `stage`, `message` | 某阶段失败 |
| `done` | `data` (object) | **最终结果** |

**done 事件的 data 结构**:
```json
{
  "content_blocks": [
    {"type": "section", "heading": "概述", "content": "CNN是一种..."},
    {"type": "code", "heading": "PyTorch实现", "content": "```python\n..."},
    {"type": "callout", "heading": "关键点", "content": "注意：卷积核大小..."},
    {"type": "mindmap", "heading": "知识图谱", "content": "{...}"},
    {"type": "mermaid", "heading": "架构图", "content": "graph TD\n..."},
    {"type": "flash_cards", "heading": "记忆闪卡", "content": "[...]"}
  ],
  "questions": [
    {
      "question_type": "choice",
      "question": "卷积核大小通常选？",
      "options": {"A": "1x1", "B": "3x3", "C": "10x10", "D": "任意"},
      "correct_answer": "B",
      "explanation": "3x3是最常用的卷积核大小..."
    }
  ],
  "resource_ids": [101, 102],
  "response": "已为你生成CNN学习资源"
}
```

**stage 枚举**（用于进度条文本）:
| stage | 含义 |
|-------|------|
| `plan` | 大纲规划 |
| `content` | 课程文档生成 |
| `mindmap` | 思维导图生成 |
| `exercise` | 练习题生成 |
| `reading` | 拓展阅读生成 |
| `code` | 代码案例生成 |
| `flashcard` | 记忆闪卡生成 |
| `review` | 质量审查 |

**前端处理**:
```javascript
eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'stage_start') {
    updateProgressBar(data.progress);
    showStageLabel(data.message); // "正在生成思维导图..."
  } else if (data.type === 'content_block') {
    renderContentBlock(data.data); // 边生成边渲染
  } else if (data.type === 'done') {
    finalizeResource(data.data.content_blocks, data.data.questions);
    eventSource.close();
  }
};
```

### 2.5 解题 — `/api/solve`

**请求**:
```json
{
  "question": "推导反向传播中权重更新的链式法则",
  "context": "",
  "user_id": 1
}
```

**SSE 事件**:
| type | 关键字段 | 说明 |
|------|----------|------|
| `steps` | `content` (array) | 解题步骤列表（一次性） |
| `token` | `content` (string) | 逐字详解 |
| `confidence` | `score` (float 0-1) | 解答置信度 |
| `done` | 无 | 结束 |

### 2.6 统一聊天 — `/api/chat`

**请求**:
```json
{
  "message": "帮我出3道决策树的题",
  "user_id": 1
}
```

**自动意图路由**:
| 用户输入 | 识别意图 | 路由到 |
|----------|----------|--------|
| "出几道CNN的题" | `exercise_gen` | `/exercise/generate` |
| "生成反向传播的学习资料" | `resource_gen` | `/resources/generate` |
| "什么是梯度下降" | `tutor_question` | `/tutor/chat` |
| "帮我规划学习路径" | `learning_path` | `/path/{id}` |
| "这道题怎么做：..." | `solve_problem` | `/solve` |
| 其他 | 默认 | `/tutor/chat` |

**响应**: 根据路由结果，返回对应接口的 SSE 流。

---

## 三、知识图谱与计划系统接口

### 3.1 知识图谱 — `GET /api/knowledge-graph/{courseId}?user_id=1`

**响应**:
```json
{
  "nodes": [
    {
      "id": "ai_overview",
      "name": "AI概述",
      "label": "AI概述",
      "difficulty": 1,
      "category": "基础",
      "description": "人工智能的基本概念与发展历程",
      "mastery": 0.65,
      "status": "learning",
      "color": {"bg": "#D6E8F0", "border": "#6AA3C4", "label": "学习中"}
    }
  ],
  "edges": [
    {
      "source": "ai_overview",
      "target": "ml_basics",
      "relation": "depends_on",
      "rationale": "AI概述是机器学习基础的前置知识"
    }
  ]
}
```

**status 枚举**: `locked`（未解锁）/ `learning`（学习中）/ `mastered`（已掌握）/ `forgotten`（已遗忘）

**color 对象**: `{bg, border, label}` — 前端直接用作节点颜色

### 3.2 节点详情卡片 — `GET /api/knowledge-graph/{courseId}/node/{nodeId}?user_id=1`

**响应**:
```json
{
  "node": {
    "id": "backprop",
    "name": "反向传播",
    "difficulty": 5,
    "mastery": 0.35,
    "status": "learning",
    "color": {"bg": "#D6E8F0", "border": "#6AA3C4", "label": "学习中"}
  },
  "performance": {
    "sub_concepts": [
      {"name": "链式法则矩阵形式", "mastery": 0.35, "tag": "学习中"},
      {"name": "常见激活函数梯度", "mastery": 0.35, "tag": "学习中"}
    ],
    "total_exercises": 12,
    "last_practiced": "2026-06-01T10:30:00"
  },
  "graph_context": {
    "prerequisites": [
      {"id": "dl_basics", "name": "深度学习基础", "status": "mastered", "mastery": 0.9, "color": {...}}
    ],
    "unlocks": [
      {"id": "gradient_variants", "name": "梯度下降变体", "status": "locked", "mastery": 0.0, "color": {...}}
    ],
    "related": [
      {"id": "overfitting", "name": "过拟合与正则化", "status": "learning", "mastery": 0.5, "color": {...}}
    ]
  },
  "actions": [
    {"label": "继续学习", "type": "primary", "target": "resource"},
    {"label": "做练习题", "type": "secondary", "target": "exercise"},
    {"label": "查看复习提醒", "type": "warning", "target": "review"}
  ]
}
```

**前端渲染建议**:
- 点击知识图谱节点 → 弹出/跳转此卡片
- `actions` 按钮直接触发对应功能（type=primary 主按钮，type=secondary 次按钮，type=warning 警告色）
- `graph_context` 节点可点击跳转
- `sub_concepts` 用进度条展示掌握度，`tag` 映射为标签颜色

### 3.3 创建计划 — `POST /api/plans/create`

**请求**:
```json
{
  "user_id": 1,
  "course_id": "ai_intro",
  "steps": [
    {"topic": "AI概述", "status": "pending", "estimated_days": 1},
    {"topic": "机器学习基础", "status": "pending", "estimated_days": 2}
  ],
  "concept_graph": { "nodes": [...], "edges": [...] }
}
```

### 3.4 计划状态 — `GET /api/plans/{planId}/status?user_id=1`

**响应**:
```json
{
  "plan_id": 1,
  "status": "paused",
  "days_idle": 14,
  "total_steps": 8,
  "completed_steps": 3,
  "soft_landing": {
    "strategy": "regression_check",
    "message": "回来了！我们先确认一下还记得什么，然后重新规划",
    "days_idle": 14,
    "review_nodes": ["反向传播", "CNN架构"],
    "decay_results": {"反向传播": "review", "CNN架构": "review_light"}
  },
  "steps": [
    {
      "id": 1,
      "step_order": 1,
      "topic": "AI概述",
      "status": "completed",
      "mastery_current": 0.9,
      "decayed_mastery": 0.85
    }
  ]
}
```

**soft_landing 三种策略**:

| strategy | 触发条件 | 含义 |
|----------|----------|------|
| `continue` | ≤ 3 天 | 直接继续，无需复习 |
| `warmup` | 4-7 天 | 做 1 道热身题，确认还记得 |
| `regression_check` | > 7 天 | 针对遗忘最严重的知识点出题检测 |

### 3.5 更新进度 — `POST /api/plans/{planId}/progress`

**请求**:
```json
{
  "user_id": 1,
  "step_id": 5,
  "status": "completed",
  "score": 0.8,
  "activity_type": "exercise",
  "duration_minutes": 25
}
```

**activity_type 枚举**: `study` / `exercise` / `quiz` / `review`

### 3.6 回归检测 — `POST /api/plans/{planId}/regression-check`

**两个阶段**：

**阶段 1 — 出题**（请求不带 answers）:
```json
// 请求
{ "user_id": 1 }

// 响应
{
  "strategy": "regression_check",
  "message": "我们先确认一下还记得什么...",
  "questions": [
    {
      "review_node": "反向传播",
      "question_type": "choice",
      "question": "离开了一段时间，一起来看看：反向传播的核心思想是？",
      "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
      "correct_answer": "B",
      "explanation": "没关系，我们一起来回顾一下..."
    }
  ]
}
```

**阶段 2 — 判分 + 重排**（请求带 answers）:
```json
// 请求
{
  "user_id": 1,
  "answers": [
    {"topic": "反向传播", "question_type": "choice", "user_answer": "B", "correct_answer": "B", "choices": ["A","B","C","D"]}
  ]
}

// 响应
{
  "strategy": "regression_check",
  "message": "很好，记忆保持得不错，按调整后的计划继续",
  "reordered_steps": [
    {"step_order": 1, "topic": "反向传播", "status": "review", "mastery_current": 0.5}
  ]
}
```

### 3.7 复习日程 — `GET /api/plans/{planId}/review-schedule?user_id=1&days_ahead=7`

**响应**:
```json
{
  "total_reviews": 4,
  "high_urgency": 2,
  "medium_urgency": 2,
  "schedule": [
    {
      "step_id": 5,
      "topic": "反向传播",
      "current_mastery": 0.35,
      "decayed_mastery": 0.12,
      "days_until_review": 0,
      "urgency": "high"
    }
  ]
}
```

**urgency 枚举**: `high`（红色，即将遗忘）/ `medium`（黄色，需关注）/ `low`（绿色，正常）

---

## 四、JSON 接口详解（非 SSE）

### 4.1 题目评分 — `POST /api/exercise/grade`

**请求**:
```json
{
  "type": "choice",
  "user_answer": "B",
  "correct_answer": "B",
  "choices": ["A", "B", "C", "D"],
  "multi": false,
  "points": 1
}
```

**响应**:
```json
{
  "correct": true,
  "score": 1,
  "earned": 1,
  "feedback": "正确！CNN的核心操作确实是卷积。"
}
```

简答题评分（type: "short_answer"）时需传 `reference_answer` 和 `rubric`。

### 4.2 错题分析 — `POST /api/exercise/error-analysis`

**请求**:
```json
{
  "errors": [
    {"question": "CNN的卷积核大小通常选？", "user_answer": "A", "correct_answer": "B"}
  ],
  "level": 2
}
```

### 4.3 评估报告 — `POST /api/evaluation/report`

**请求**:
```json
{
  "evaluation_results": {
    "answers": [
      {"question_id": "q1", "correct": true, "score": 1},
      {"question_id": "q2", "correct": false, "score": 0}
    ]
  },
  "user_id": 1
}
```

**响应**:
```json
{
  "overall_score": 75,
  "dimension_scores": {"knowledge_base": 80, "weak_points": 60},
  "strengths": ["基础概念理解扎实"],
  "weaknesses": ["数学推导能力弱"],
  "suggestions": ["建议重点复习链式法则和矩阵求导"]
}
```

---

## 五、数据结构速查

### 5.1 学生画像
```json
{
  "knowledge_base": 50,
  "cognitive_style": "visual",
  "learning_goal": "掌握深度学习",
  "weak_points": ["数学", "Python"],
  "learning_pace": "moderate",
  "interest_direction": ["CV", "NLP"],
  "entries": {
    "weak_points": [
      {"text": "反向传播推导", "confidence": 7, "status": "active", "created_at": "..."}
    ],
    "interest_direction": [
      {"text": "计算机视觉", "confidence": 3, "status": "tentative", "created_at": "..."}
    ]
  }
}
```

### 5.2 学习路径
```json
{
  "steps": [
    {"order": 1, "topic": "AI概述", "status": "pending", "estimated_days": 1}
  ],
  "concept_graph": {
    "nodes": [
      {"id": "ai_overview", "label": "AI概述", "description": "...", "weight": 0.3}
    ],
    "edges": [
      {"src": "ai_overview", "dst": "ml_basics", "relation": "depends_on", "rationale": "..."}
    ]
  }
}
```

### 5.3 题目结构
```json
{
  "question_type": "choice",
  "question": "以下哪项是监督学习算法？",
  "options": {"A": "K-Means", "B": "决策树", "C": "PCA", "D": "DBSCAN"},
  "correct_answer": "B",
  "explanation": "决策树需要标签数据进行训练，属于监督学习。"
}
```

### 5.4 画像完整度
```json
{
  "is_complete": false,
  "filled_dimensions": 4,
  "total_dimensions": 6,
  "missing_dimensions": ["learning_goal", "learning_pace"],
  "completion_percentage": 67
}
```

---

### 5.5 知识图谱候选节点交互

**触发时机**: 统一聊天 `/api/chat` SSE 流中，AI 在完成回答后可能发送 `knowledge_graph_candidates` 事件。

**SSE 事件格式**:
```json
{
  "type": "content",
  "stage": "knowledge_graph",
  "message": "检测到新知识节点候选",
  "data": {
    "type": "knowledge_graph_candidates",
    "question": "检测到以下新概念，是否加入知识图谱？",
    "primary": [{"id": "cnn_basics", "name": "CNN基础", "type": "concept", ...}],
    "related": [{"id": "pooling_layers", "name": "池化层", "type": "concept", ...}],
    "broad": [{"id": "image_processing", "name": "图像处理基础", "type": "concept", ...}],
    "candidates": [...]  // primary + related + broad 的合集
  }
}
```

**前端交互流程**:
```
1. 收到 knowledge_graph_candidates 事件
2. 弹窗展示候选节点，按 primary/related/broad 分三组
3. 用户勾选想添加的节点 → 点击「确认加入」
4. 调用 POST /api/graph/nodes
   body: {
     "course_id": "ai_intro",
     "updates": [{"action": "add_node", "data": {选择节点}}]
   }
5. 调用 GET /api/knowledge-graph/{courseId}?user_id=1 刷新图谱
```

**分组含义**:
| 分组 | 含义 | 前端展示建议 |
|------|------|-------------|
| `primary` | 核心概念，强烈建议加入 | 蓝色标记，默认勾选 |
| `related` | 相关概念，建议加入 | 默认勾选 |
| `broad` | 拓展概念，可选 | 默认不勾选 |

---

## 六、前端对接检查清单

- [ ] SSE 流式接口使用 `fetch + ReadableStream`（非 EventSource，因为需要 POST）
- [ ] 所有 SSE 接口设置 120 秒超时
- [ ] 知识图谱节点用 `color` 对象直接渲染（bg=填充色, border=边框色）
- [ ] 节点状态 `status` 用图标区分（locked=🔒, learning=📖, mastered=✅, forgotten=⚠️）
- [ ] 资源中心支持 6 种资源类型（section/code/callout/mindmap/mermaid/flash_cards）
- [ ] 资源生成进度条绑定 `progress` 字段，显示当前 `stage` 文本
- [ ] 答疑使用 `content + conversation_id` 方式，保存并回传 `conversation_id`
- [ ] 画像面板的 `entries` 区分 `active`（实色）和 `tentative`（浅色/问号图标）
- [ ] 节点详情卡片 `actions` 按钮按 `type` 渲染（primary=主色, secondary=次色, warning=警告色）
- [ ] `soft_landing.strategy` 为 `regression_check` 时走回归检测两阶段流程
- [ ] 复习日程 `urgency: high` 用红色标记提醒
- [ ] 统一聊天入口 `/api/chat` 作为万能输入框
- [ ] 知识图谱候选节点 `knowledge_graph_candidates` 弹窗确认 → 调 `/graph/nodes` 落地
- [ ] 所有接口错误处理（网络超时 + AI 服务不可用）

---

> **维护者**: AI 服务（Python 内核）
> **最后更新**: 2026-06-05
> **参考**: `archive/temp_file/归档/（旧参考，原前端任务追加指导书）` / `archive/temp_file/归档/API_CONTRACT.md` / `archive/docs/归档/前端战神任务说明书.docx`
