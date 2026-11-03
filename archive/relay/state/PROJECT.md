# PROJECT｜项目长期地图（总督维护，建议 < 120 行）

- 项目名：智学云 DeepTutor（基于大模型的个性化学习多智能体系统）；README 已定位为个人主导的 Agent 工程项目。
- 目标用户 / 成功结果：学生在 AI Tutor 对话中得到结构清晰、公式和可视化正确渲染的回答。
- 技术栈：
  - ai-service：Python，FastAPI + LangGraph，多 Agent 编排、路由、质量门、流式输出。主线。
  - frontend：Vue 3.5 + TypeScript + Vite 8 + Pinia + Element Plus + Tailwind 4；Markdown 用 marked + KaTeX + DOMPurify；Mermaid 另有渲染；测试用 Vitest。
  - backend（Java / Spring Boot）：参照与演示边界，不作为维护主线。
- 启动 / 验证命令：
  - 前端：在 `frontend/` 下 `npm run dev`；测试 `npx vitest run`；类型检查 `npm run type-check`。锁文件为 `pnpm-lock.yaml`。
  - 后端：`ai-service/` 下的 Python 服务，入口 `ai-service/main.py`。
  - 本机注意：`python3` 是 Windows 应用商店占位桩（退出码 49），执行 Python 用 `/d/Anaconda/python`。
- 核心业务入口（路径，不复制源码）：
  - 对话正文渲染单一入口：`frontend/src/utils/markdown.ts`（`renderChatMarkdown`）。
  - 对话消息列表：`frontend/src/components/chat/ChatThread.vue`。
  - 页面：`frontend/src/views/AITutor.vue`、`ProfileChat.vue`；`CourseDetail.vue` 仍直接用全局 marked。
  - Tutor 提示词：`ai-service/prompts/tutor_agent/system.yaml`。
- 模块边界与重要依赖：
  - 前后端通过 SSE 流式事件通信。
  - 聊天界面优化的设计参考在 `docs/聊天界面优化/reference/`（`tutor_attention_implementation.md` 为规格，`tutor_attention_design.html` 为不依赖框架的视觉原型，不等于已接入组件）。
  - 路由/智能体架构线的审计与基线材料在 `docs/agent-engineering/`，与 relay 任务队列相互独立。
- 当前已知问题：
  - 助手回答中行内 `$n$` 与 `**token**` 仍可能以源码出现（T001 排查中）。
  - 工作树有大量未提交改动，涉及 ai-service 路由/工具/联网相关文件，以及 frontend 的 ChatThread、AITutor、Home、ProfileChat、main.ts、package.json、lockfile、markdown.ts 等。派发任务必须以现状为基线。
  - `relay/` 与 `.claude/` 目录目前未跟踪。
- 不可变约束：
  - 不覆盖用户未提交变更；不做 `git checkout` / `stash` / `reset` 等会丢工作的操作。
  - 不自动提交、不推送；提交需用户明确授权。
  - 文本渲染问题不通过修改 AI 提示词解决。
  - AttentionMatrix 颜色只表示可访问关系（mask），无真实权重时不输出强弱或概率。

> 这里只写跨任务仍有效的事实；短期进展写 QUEUE，短期交接写 GOVERNOR_WILL。
