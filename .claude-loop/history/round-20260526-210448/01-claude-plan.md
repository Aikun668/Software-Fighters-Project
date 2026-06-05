# Claude 计划 | Round DAY01-005 | 2026-05-26

## 任务 ID
TASK-DAY01-005

## 任务类型
feature（API 层）

## 目标
完善 4 个 Mock SSE 端点，让前端和 Java 后端可以用逼真的假数据开始开发。同时解决 internal_api.py 和 main.py 各自创建 FastAPI app 的架构冲突。

## 背景
`internal_api.py` 已有一个骨架版本，但有两个问题：
1. **Mock 数据太假**：每个端点只返回 1 个 token + done，前端没法测试流式渲染效果
2. **架构冲突**：internal_api.py（第18行）和 main.py 各自创建了独立的 FastAPI app，都绑 8001 端口。需要合并

## 验收标准
- [ ] 4 个端点返回的 mock 数据够逼真（≥5 个 token 的流式输出）
- [ ] internal_api.py 的路由被挂载到 main.py 的 app 上（不再独立创建 app）
- [ ] SSE 格式统一：`data: {"type":"token"/"progress"/"done", "content":"..."}\n\n`
- [ ] 启动 main.py 后 4 个端点都可以访问
- [ ] curl 测试每个端点都能返回正确的 SSE 流

## 关键文件
| 文件路径 | 操作 | 说明 |
|---------|------|------|
| ai-service/internal_api.py | 修改 | 丰富 mock 数据，改为 APIRouter 模式 |
| ai-service/main.py | 修改 | include_router 引入 internal_api 的路由 |

## 约束条件
- 不修改 llm_service.py、base_agent.py、models/
- 不实现真实 LLM 调用（那是 Day 2+ 的任务）
- SSE 格式必须跟最终真实版本一致

## 验证方式
```bash
cd ai-service
# 启动服务
venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8001

# 另开终端测试（每个端点都要测）
curl -N -X POST http://localhost:8001/internal/tutor/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"什么是机器学习？"}]}'
# 预期：逐行输出 5+ 个 data: {"type":"token","content":"..."} 然后 data: {"type":"done"}

curl http://localhost:8001/internal/path/student-001
# 预期：返回 JSON，包含 steps 数组
```

## 给 DeepSeek 的注意事项

### 架构改造：从独立 app → APIRouter

当前问题：
```python
# internal_api.py（当前）
app = FastAPI()  # 自己创建了一个 app，跟 main.py 冲突

# main.py（当前）
app = FastAPI()  # 另一个 app
```

修复后：
```python
# internal_api.py
router = APIRouter(prefix="/internal")  # 改为 router

# main.py
from internal_api import router as internal_router
app.include_router(internal_router)  # 挂载进来
```

### 4 个 Mock 端点的 mock 数据设计

**1. POST /internal/profile/chat**（对话式画像构建）
模拟一段画像构建对话，至少 8 个 token：
```
"你好！我是你的AI学习助手。让我了解一下你的学习情况..."
"看起来你有Python基础，但对机器学习还不太熟悉。"
"我建议从监督学习开始，这是最直观的入门方式。"
"根据我们的对话，你的认知风格偏向视觉型学习。"
```
中间穿插 `profile_update` 类型的 SSE 事件。

**2. POST /internal/resources/generate**（资源生成）
模拟两阶段生成流程，展示进度：
```
data: {"type":"progress","stage":"outline","content":"正在分析知识点结构..."}
data: {"type":"progress","stage":"outline","content":"大纲生成完成：1.基础概念 2.核心算法 3.实践案例"}
data: {"type":"progress","stage":"generating","content":"正在生成课程文档..."}
data: {"type":"progress","stage":"generating","content":"正在生成思维导图..."}
data: {"type":"progress","stage":"generating","content":"正在生成练习题..."}
data: {"type":"progress","stage":"generating","content":"正在生成拓展阅读..."}
data: {"type":"progress","stage":"generating","content":"正在生成代码案例..."}
data: {"type":"done"}
```

**3. POST /internal/tutor/chat**（智能答疑）
模拟答疑对话，至少 5 个 token，包含 Markdown 内容：
```
"卷积神经网络（CNN）是一种专门处理网格结构数据的深度学习架构。\n\n"
"**核心组件：**\n1. 卷积层 - 提取局部特征\n2. 池化层 - 降维\n3. 全连接层 - 分类\n\n"
"```python\nmodel = Sequential([\n    Conv2D(32, 3, activation='relu'),\n    MaxPooling2D(2),\n    Dense(10, activation='softmax')\n])\n```"
```
中间也穿插 token 事件（不是一次性返回）。

**4. GET /internal/path/{student_id}**（学习路径）
返回一个包含 5 个步骤的 JSON：
```json
{
  "student_id": "student-001",
  "steps": [
    {"order": 1, "topic": "Python 基础回顾", "status": "completed", "resource_id": null},
    {"order": 2, "topic": "机器学习概述", "status": "completed", "resource_id": null},
    {"order": 3, "topic": "监督学习算法", "status": "in_progress", "resource_id": null},
    {"order": 4, "topic": "神经网络基础", "status": "pending", "resource_id": null},
    {"order": 5, "topic": "深度学习实践", "status": "pending", "resource_id": null}
  ]
}
```

### SSE 格式（重要，前后端都依赖这个）

每行格式：`data: {json}\n\n`

三种事件类型：
- `token` — 流式文本片段，前端逐字显示
- `progress` — 进度更新，前端显示进度条
- `profile_update` — 画像更新，前端更新画像面板
- `done` — 流结束

### main.py 改动

只需要加两行：
```python
from internal_api import router as internal_router
app.include_router(internal_router)
```

---
产出文件：.claude-loop/active/01-claude-plan.md | Round DAY01-005
