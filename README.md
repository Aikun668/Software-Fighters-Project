# Software-Fighters

> 中国软件杯 · 基于大模型的个性化资源生成与学习多智能体系统

## 项目简介

面向「人工智能导论」课程，用 5 个不同角色的 AI Agent 协同工作，实现：

1. **对话式学生画像构建** —— 6 维动态画像（知识基础 / 认知风格 / 学习目标 / 易错点 / 学习节奏 / 兴趣方向）
2. **多智能体协同生成 5 种资源** —— 课程文档 / 思维导图 / 练习题 / 拓展阅读 / 代码案例
3. **个性化学习路径规划 + 多模态答疑** —— 知识图谱路径 + 图文公式问答

## 技术栈

| 层 | 技术 |
|---|------|
| 前端 | Vue 3 + TypeScript + Element Plus + Pinia + Vite |
| 后端 | FastAPI + SQLAlchemy 2.0 + PostgreSQL |
| AI 引擎 | LangGraph + 讯飞星火 Spark API + ChromaDB |
| 多智能体 | 画像 Agent / 内容生成 Agent / 题目 Agent / 路径规划 Agent / 答疑 Agent |

## 项目结构

`
Software-Fighters-Project/
├── backend/
│   ├── app/
│   │   ├── agents/          # 5 个智能体定义（队长负责）
│   │   ├── workflows/       # LangGraph 工作流编排（队长负责）
│   │   ├── services/        # LLM 封装 + 知识库检索（队长负责）
│   │   ├── api/             # FastAPI 路由（后端同学负责）
│   │   ├── models/          # SQLAlchemy 模型（后端同学负责）
│   │   └── db/              # 数据库配置（后端同学负责）
│   ├── prompts/             # 5 个 Agent 的 Prompt 模板（YAML）
│   └── knowledge_data/      # 知识库原始文档
├── frontend/src/             # Vue 3 前端（前端同学负责）
│   ├── views/               # 页面
│   ├── components/          # 组件
│   ├── stores/              # Pinia 状态
│   ├── api/                 # 请求封装
│   └── router/              # 路由
└── docs/                    # 项目文档
`

## 快速开始

`ash
# 克隆项目
git clone <repo-url>
cd Software-Fighters-Project

# 切换到你的分支
git checkout agent-dev      # 队长
git checkout backend-dev    # 后端
git checkout frontend-dev   # 前端

# 安装后端依赖
cd backend
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入星火 API Key 等

# 启动后端（后端同学完善 main.py 后）
uvicorn main:app --reload
`

## 分支规范

| 分支 | 负责人 | 说明 |
|------|--------|------|
| main | 队长合并 | 主分支，只接受 PR |
| gent-dev | 队长 | 多智能体 + LangGraph 开发 |
| ackend-dev | 后端同学 | FastAPI + DB + 知识库入库 |
| rontend-dev | 前端同学 | Vue 3 全部页面 |

## 团队

- **队长（算法kun）**：多智能体系统核心、LangGraph 编排、LLM 封装、知识库检索
- **后端同学**：FastAPI 路由、数据库、ChromaDB 知识库管理
- **前端同学**：Vue 3 全部页面、SSE 流式对接、Markdown/思维导图渲染
