# Claude 计划 | Round DAY01-002 | 2026-05-26

## 任务 ID
TASK-DAY01-002

## 任务类型
infra（基础设施搭建）

## 目标
搭建 Python AI 微服务的基础环境：虚拟环境 + 依赖安装 + FastAPI 骨架 + 健康检查端点

## 背景
Day 1 的核心目标是让 Python AI 微服务能独立启动。需要先搭建好 Python 虚拟环境，安装依赖，然后创建 FastAPI 入口文件和健康检查端点。

## 验收标准
- [ ] Python 虚拟环境已创建（ai-service/venv/）
- [ ] 依赖已安装成功（requirements.txt 中的所有包）
- [ ] 可以成功 import 关键包：langgraph, fastapi, chromadb, aiomysql
- [ ] ai-service/main.py 已创建，包含 FastAPI 应用实例
- [ ] /health 健康检查端点已实现，返回 {"status": "ok"}
- [ ] 服务可以启动：uvicorn main:app --reload --port 8001
- [ ] 访问 http://localhost:8001/health 返回 200
- [ ] 访问 http://localhost:8001/docs 可以看到 Swagger 文档

## 关键文件
| 文件路径 | 操作 | 说明 |
|---------|------|------|
| ai-service/venv/ | 新建 | Python 虚拟环境目录 |
| ai-service/main.py | 新建 | FastAPI 入口文件 |
| ai-service/.env | 新建 | 环境变量配置（包含讯飞星火 API Key） |

## 约束条件
- 不修改 requirements.txt
- 不修改 app/ 目录下的任何文件（还没创建）
- 不实现业务逻辑，只搭建骨架

## 验证方式
```bash
# 1. 验证虚拟环境
cd ai-service
source venv/bin/activate  # Windows: venv\Scripts\activate
python --version  # 应该显示 Python 3.9+

# 2. 验证依赖安装
python -c "import langgraph, fastapi, chromadb, aiomysql; print('所有依赖导入成功')"

# 3. 启动服务
uvicorn main:app --reload --port 8001
# 应该看到：Uvicorn running on http://127.0.0.1:8001

# 4. 测试健康检查（另一个终端）
curl http://localhost:8001/health
# 应该返回：{"status":"ok"}

# 5. 测试 Swagger 文档
curl http://localhost:8001/docs
# 应该返回 HTML 页面
```

## 给 DeepSeek 的注意事项

### main.py 结构建议
- 使用 FastAPI() 创建应用实例
- 配置 CORS（允许 localhost:8080 访问）
- 实现 /health 端点（GET 请求，返回 JSON）
- 添加 Swagger 文档标题和描述
- 不要实现业务逻辑，只搭建骨架

### .env 文件内容
需要包含以下环境变量（用户已经拿到了讯飞星火 API Key）：
```
# 讯飞星火 API
SPARK_API_KEY=你的API_KEY
SPARK_API_SECRET=你的API_SECRET

# 数据库（MySQL）
DATABASE_URL=mysql+aiomysql://root:password@localhost:3306/ai_edu

# ChromaDB
CHROMA_PERSIST_PATH=./chroma_data
CHROMA_COLLECTION=ai_intro
```

### 虚拟环境创建
- Windows: `python -m venv venv`
- 激活: `venv\Scripts\activate`
- 安装依赖: `pip install -r requirements.txt`

---
产出文件：.claude-loop/active/01-claude-plan.md | Round DAY01-002
