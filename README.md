# Software-Fighters

> 中国软件杯 · 基于大模型的个性化资源生成与学习多智能体系统

## 项目简介

面向「人工智能导论」课程，5 个 AI Agent 协同工作：

1. **对话式学生画像构建** — 6 维动态画像
2. **多智能体协同生成 5 种资源** — 文档 / 思维导图 / 题目 / 拓展阅读 / 代码案例
3. **个性化学习路径规划 + 多模态答疑**

## 架构

`
浏览器 (Vue 3)
       |
       v
Java SpringBoot (:8080)
  认证 / CRUD / Redis / 文件
  controller -> service -> mapper
       |
       | HTTP (localhost:8001)
       v
Python FastAPI (:8001, 仅内网)
  LangGraph / 5 Agent / 星火 Spark / ChromaDB
`

## 技术栈

| 层 | 技术 |
|---|------|
| 前端 | Vue 3 + TypeScript + Element Plus + Pinia + Vite |
| 主后端 | Java SpringBoot 3 + MyBatisPlus + Redis + JWT |
| AI 微服务 | Python FastAPI + LangGraph + ChromaDB |
| 大模型 | 讯飞星火 Spark API |
| 数据库 | PostgreSQL |

## 项目结构

```
Software-Fighters-Project/
    ai-service/                  Python AI [队长]
        app/agents/              5 个 Agent 定义
        app/workflows/           LangGraph 编排
        app/services/            LLM 封装 + 知识库
        prompts/                 Prompt YAML 模板
        internal_api.py          对 Java 的内部 HTTP 接口
        knowledge_data/          知识库文档
        requirements.txt
    backend/                     Java SpringBoot [后端]
        src/main/java/.../
            controller/          REST 控制器
            service/             业务逻辑
            mapper/              MyBatisPlus
            entity/              实体类
            config/              配置
        src/main/resources/
            application.yml
        pom.xml
    frontend/                    Vue 3 [前端]
        src/views/
        src/components/
        src/stores/
        src/api/
        src/router/
    docs/                        项目文档
```

## 快速开始

`bash
git clone https://github.com/Aikun668/Software-Fighters-Project.git
cd Software-Fighters-Project

# ---- Python AI 微服务 ----
cd ai-service
pip install -r requirements.txt
cp .env.example .env          # 编辑 .env 填入星火 API Key
python internal_api.py         # 启动 -> localhost:8001

# ---- Java 后端 ----
cd backend
./mvnw spring-boot:run         # 启动 -> localhost:8080

# ---- 前端 ----
cd frontend
pnpm install
pnpm dev                       # 启动 -> localhost:5173
`

## AI 微服务内部接口

> Python 微服务只监听 127.0.0.1:8001，不对外暴露。Java 通过 HTTP 调用。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /internal/profile/chat | SSE 流式画像对话 |
| POST | /internal/resources/generate | SSE 流式资源生成 |
| POST | /internal/tutor/chat | SSE 流式答疑 |
| GET | /internal/path/{student_id} | 学习路径 JSON |

## 分支

| 分支 | 负责人 | 说明 |
|------|--------|------|
| main | 队长 | 主分支，最终合并 |
| agent-dev | 队长 | Python AI Agent 开发 |
| backend-dev | 后端 | Java SpringBoot 开发 |
| rontend-dev | 前端 | Vue 3 开发 |

## 团队

| 角色 | 职责 |
|------|------|
| **队长** | Python 多智能体核心 · LangGraph 编排 · 星火 API 封装 · ChromaDB |
| **后端** | Java SpringBoot · MyBatisPlus · Redis · 数据库 · 知识库入库 |
| **前端** | Vue 3 页面 · SSE 流式 · Markdown/思维导图渲染 |
