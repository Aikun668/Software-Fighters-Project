# Software-Fighters

> 中国软件杯 · 基于大模型的个性化资源生成与学习多智能体系统

## 项目简介

面向「人工智能导论」课程，用 5 个不同角色的 AI Agent 协同工作，实现：

1. **对话式学生画像构建** —— 6 维动态画像
2. **多智能体协同生成 5 种资源** —— 文档 / 思维导图 / 题目 / 拓展阅读 / 代码案例
3. **个性化学习路径规划 + 多模态答疑**

## 架构

`
浏览器 (Vue 3)
    |
    V
Java SpringBoot (主后端 :8080)
  认证鉴权 / CRUD / Redis / 文件上传
  controller -> service -> mapper
    |
    | HTTP (localhost:8001)
    V
Python FastAPI (AI 微服务)
  LangGraph 5 Agent / 星火 Spark / ChromaDB
`

| 技术 | 用途 |
|------|------|
| Vue 3 + Element Plus + Pinia | 前端 |
| Java SpringBoot 3 + MyBatisPlus + Redis | 主后端（三层架构） |
| Python FastAPI + LangGraph + ChromaDB | AI 微服务 |
| 讯飞星火 Spark API | 大模型 |
| PostgreSQL | 数据库 |

## 项目结构

`
Software-Fighters-Project/
|-- ai-service/                  # Python AI (队长)
|   |-- app/agents/              # 5 个 Agent 定义
|   |-- app/workflows/           # LangGraph 编排
|   |-- app/services/            # LLM 封装 + 知识库
|   |-- prompts/                 # Prompt YAML 模板
|   |-- internal_api.py          # 对 Java 暴露的内部 HTTP 接口
|   |-- knowledge_data/          # 知识库原始文档
|   |-- requirements.txt
|
|-- backend/                     # Java SpringBoot (后端同学)
|   |-- src/main/java/.../
|   |   |-- controller/          # REST 控制器
|   |   |-- service/             # 业务逻辑
|   |   |-- mapper/              # MyBatisPlus 数据访问
|   |   |-- entity/              # 实体类
|   |   |-- config/              # 配置
|   |-- src/main/resources/
|   |   |-- application.yml
|   |-- pom.xml
|
|-- frontend/                    # Vue 3 (前端同学)
|   |-- src/views/
|   |-- src/components/
|   |-- src/stores/
|   |-- src/api/
|   |-- src/router/
|
|-- docs/                        # 项目文档
`

## 快速开始

`ash
git clone <repo-url>
cd Software-Fighters-Project

# ---- Python AI 微服务 ----
cd ai-service
pip install -r requirements.txt
cp .env.example .env   # 填入星火 API Key
python internal_api.py  # 启动在 localhost:8001

# ---- Java 后端 ----
cd backend
./mvnw spring-boot:run   # 启动在 localhost:8080

# ---- 前端 ----
cd frontend
pnpm install
pnpm dev                 # 启动在 localhost:5173
`

## AI 微服务内部接口（Python -> Java 调用）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /internal/profile/chat | SSE 流式画像对话 |
| POST | /internal/resources/generate | SSE 流式资源生成 |
| POST | /internal/tutor/chat | SSE 流式答疑 |
| GET | /internal/path/{student_id} | 学习路径 JSON |

## 分支

| 分支 | 负责人 | 说明 |
|------|--------|------|
| main | 队长合并 | 主分支 |
| gent-dev | 队长 | Python AI Agent 开发 |
| ackend-dev | 后端同学 | Java SpringBoot 开发 |
| rontend-dev | 前端同学 | Vue 3 开发 |

## 团队

- **队长**：Python 多智能体系统核心、LangGraph 编排、星火 API 封装、ChromaDB
- **后端同学**：Java SpringBoot + MyBatisPlus + Redis、数据库设计、知识库入库
- **前端同学**：Vue 3 全部页面、SSE 流式对接、Markdown/思维导图渲染
