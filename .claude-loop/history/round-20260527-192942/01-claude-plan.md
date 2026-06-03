# Claude 计划 | Round DAY03-001 | 2026-05-27

## 任务 ID
TASK-DAY03-001

## 任务类型
feature（4 Agent 骨架搭建）

## 目标
把另外 4 个 Agent（Tutor / Content / Exercise / Path）的 prompt 文件 + Python 类 + API 端点全部搭起来。全部 Mock 模式可跑通。

## 背景
Day 2 完成了 ProfileAgent + Spark API + Prompt Loader 体系。现在项目里 4 个 Agent 的 `prompts/*/system.yaml` 全是占位符文字，`internal_api.py` 的对应端点也是硬编码 mock 数据。

**搬运策略**：从参考项目 `DeepTutor-参考版` 直接复制 YAML prompt 文件，改角色名 + 变量名 → 直接用。每个 Agent 改动量 < 20%。

**参考项目位置**：
- `D:\My_Grand_Projects2026\Software-Cup-Game2026\DeepTutor-参考版\deeptutor\`（prompt 源）
- `D:\My_Grand_Projects2026\Software-Cup-Game2026\Software-Fighters-Project\ai-service\`（目标项目）

## 验收标准
- [ ] 4 个 Agent 的 YAML prompt 文件全部从 DeepTutor 搬运完毕，变量名/角色名适配完成
- [ ] 4 个 Python Agent 类（tutor_agent / content_agent / exercise_agent / path_agent）全部创建，继承 BaseAgent
- [ ] 4 个 API 端点从 mock 替换为真实 Agent 调用，Mock 模式下可跑通
- [ ] `python test_spark_api.py` 全部通过（Spark API 不能坏）
- [ ] Mock 模式端到端测试：每个端点返回正确的 SSE 流 + 合理内容

## 搬运清单

### 搬什么（10 个 YAML 源文件 → 11 个目标文件）

| 源文件（DeepTutor-参考版） | 目标文件（ai-service） | 功能 |
|---|---|---|
| `deeptutor/agents/chat/prompts/zh/chat_agent.yaml` | `prompts/tutor_agent/system.yaml` | 答疑角色+回复规则+RAG注入 |
| `deeptutor/book/prompts/en/page_planner.yaml` | `prompts/content_agent/system.yaml` | 内容编排总控 |
| `deeptutor/book/prompts/en/section.yaml` | `prompts/content_agent/outline.yaml` | 课程大纲生成 |
| `deeptutor/book/prompts/en/code.yaml` | `prompts/content_agent/code.yaml` | Python 代码案例 |
| `deeptutor/book/prompts/en/deep_dive.yaml` | `prompts/content_agent/deep_dive.yaml` | 拓展阅读材料 |
| `deeptutor/book/prompts/en/flash_cards.yaml` | `prompts/content_agent/mindmap.yaml` | 思维导图节点 |
| `deeptutor/agents/question/prompts/zh/pipeline.yaml` | `prompts/exercise_agent/pipeline.yaml` | 3阶段出题流水线 |
| `deeptutor/agents/question/prompts/zh/followup_agent.yaml` | `prompts/exercise_agent/followup.yaml` | 错题讲解 |
| — | `prompts/exercise_agent/system.yaml` | 从 pipeline.yaml 拆出角色定义部分 |
| `deeptutor/book/prompts/en/spine_synthesizer.yaml` | `prompts/path_agent/system.yaml` | 路径生成（draft→critique→revise） |
| `deeptutor/book/prompts/en/spine_agent.yaml` | `prompts/path_agent/path_planner.yaml` | 步骤树设计 |

### 变量改名规则
所有搬运文件中的变量做以下批量替换：
- `{chapter_title}` / `{chapter_summary}` / `{objectives_block}` → `{topic}` / `{topic_summary}` / `{objectives}`
- `{rag_section}` / 检索结果占位符 → `{knowledge_context}`
- `{quiz_history}` → `{weak_points}`
- `{num_questions}` → `{count}`
- `{proposal_block}` / `{source_material}` → `{student_profile}` / `{knowledge_context}`
- 角色名 "DeepTutor" → "Software-Fighters"
- 所有 prompt 新增 `{student_profile}` 变量注入点（用于个性化）

## 4 个 Agent 结构设计

### Agent 1：TutorAgent（最简单，先做）

**StateGraph**：2 节点 linear — `retrieve` → `respond`

**State 字段**：messages, user_id, student_profile, knowledge_context, response

**LLM 配置**：temperature=0.7，流式 chat_stream()

**关键决策**：
- retrieve 节点从 ChromaDB 检索（当前 mock：返回空字符串或硬编码文本片段）
- respond 节点注入 `{student_profile}` + `{knowledge_context}` 到 prompt
- 角色：智能答疑助手，基于 RAG 上下文回答

### Agent 2：ContentAgent

**StateGraph**：2 节点 linear — `plan` → `generate`

**State 字段**：topic, student_profile, outline(dict), current_section(str), stage(str)

**LLM 配置**：plan 节点 temperature=0.3 非流式（JSON 输出），generate 节点 temperature=0.7 流式

**关键决策**：
- plan 节点加载 outline.yaml prompt，生成课程大纲 JSON
- generate 节点按大纲逐块生成内容，每块一个 SSE progress 事件
- code/deep_dive/mindmap 作为 generate 的子 prompt，按内容类型选择

### Agent 3：ExerciseAgent（最复杂）

**StateGraph**：3 节点 linear — `plan` → `generate` → `review`

**State 字段**：topic, count, difficulty, student_profile, plan(list), questions(list), stage(str)

**LLM 配置**：plan 用 temperature=0.3 非流式，generate 用 temperature=0.7

**关键决策**：
- pipeline.yaml 是 DeepTutor 最完整的 prompt 体系（3 阶段 explore/plan/quiz_step）
- 搬运时把 explore 阶段的角色定义拆到 system.yaml，plan + quiz_step 留在 pipeline.yaml
- 6 种题型 JSON schema 完全复用：choice / concept / fill_in_blank / short_answer / written / coding
- 薄弱点诊断逻辑：从 student_profile.weak_points 推断出题方向
- followup.yaml 用于错题讲解（review 节点）

### Agent 4：PathAgent

**StateGraph**：2 节点 — `draft` → `revise`（非流式两次调用）

**State 字段**：student_id, student_profile, concept_graph(dict), steps(list), critique(str), version(int)

**LLM 配置**：两个节点都用 temperature=0.3 非流式（结构化输出）

**关键决策**：
- spine_synthesizer 的 3 阶段（draft→critique→revise）缩减为 draft→revise 2 节点
- critique 内容内嵌在 revise 节点的 prompt 中（让 LLM 先自我审查再修正）
- 概念图 nodes/edges JSON 结构完全复用
- 输出新增 steps 数组：order, topic, status, resource_id

## 关键文件

| 文件路径 | 操作 | 说明 |
|---------|------|------|
| `prompts/tutor_agent/system.yaml` | 修改 | 从 DeepTutor chat_agent.yaml 搬运+适配 |
| `prompts/content_agent/system.yaml` | 修改 | 从 DeepTutor page_planner.yaml 搬运 |
| `prompts/content_agent/outline.yaml` | 新建 | 从 DeepTutor section.yaml 搬运 |
| `prompts/content_agent/code.yaml` | 新建 | 从 DeepTutor code.yaml 搬运 |
| `prompts/content_agent/deep_dive.yaml` | 新建 | 从 DeepTutor deep_dive.yaml 搬运 |
| `prompts/content_agent/mindmap.yaml` | 新建 | 从 DeepTutor flash_cards.yaml 搬运 |
| `prompts/exercise_agent/system.yaml` | 修改 | 从 DeepTutor pipeline Phase1 拆出 |
| `prompts/exercise_agent/pipeline.yaml` | 新建 | 从 DeepTutor pipeline.yaml 完整搬运 |
| `prompts/exercise_agent/followup.yaml` | 新建 | 从 DeepTutor followup_agent.yaml 搬运 |
| `prompts/path_agent/system.yaml` | 修改 | 从 DeepTutor spine_synthesizer.yaml 搬运 |
| `prompts/path_agent/path_planner.yaml` | 新建 | 从 DeepTutor spine_agent.yaml 搬运 |
| `app/agents/tutor_agent.py` | 新建 | TutorAgent 类 |
| `app/agents/content_agent.py` | 新建 | ContentAgent 类 |
| `app/agents/exercise_agent.py` | 新建 | ExerciseAgent 类 |
| `app/agents/path_agent.py` | 新建 | PathAgent 类 |
| `internal_api.py` | 修改 | 4 个 endpoint 从 mock 改为真实 Agent |

## 约束条件
- **不能破坏**：BaseAgent、SparkLLM、prompt_loader、ProfileAgent 的现有接口
- **不能修改**：app/models/、app/db/、app/services/llm_service.py、app/utils/prompt_loader.py
- **所有 Agent 默认 use_mock_llm=True**（真实 API 调用是可选的，通过环境变量控制）
- **沿用现有模式**：每个 Agent 继承 BaseAgent，用 LangGraph StateGraph，配 YAML prompt
- Prompt 搬运时保留原文件结构（system/user 分区、变量名风格），只改必要的角色名和变量名

## 验证方式

```bash
# 0. 前置验证：Spark API 仍然可用
cd ai-service && python test_spark_api.py

# 1. 模块导入验证
python -c "
from app.agents.tutor_agent import TutorAgent
from app.agents.content_agent import ContentAgent
from app.agents.exercise_agent import ExerciseAgent
from app.agents.path_agent import PathAgent
print('All 4 agents imported OK')
"

# 2. Mock 模式单元测试
python -c "
import asyncio
from app.agents.tutor_agent import TutorAgent
agent = TutorAgent(use_mock_llm=True)
state = asyncio.run(agent.run({
    'messages': [{'role':'user','content':'什么是CNN？'}],
    'user_id': 1,
    'student_profile': {},
}))
print('response:', state.get('response','')[:100])
"

# 3. API 端点测试
# 启动服务：venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8001
curl -X POST http://localhost:8001/internal/tutor/chat -H "Content-Type: application/json" -d '{"user_id":1, "messages":[{"role":"user","content":"什么是CNN？"}]}'
curl -X POST http://localhost:8001/internal/resources/generate -H "Content-Type: application/json" -d '{"student_id":"1", "topic":"机器学习基础"}'
curl -X POST http://localhost:8001/internal/exercise/generate -H "Content-Type: application/json" -d '{"topic":"决策树", "count":3, "difficulty":"medium"}'
curl http://localhost:8001/internal/path/1
```

## 给 Builder 的注意事项

### 执行顺序
先搬运 prompt 文件（纯文本复制），再建 Python 类，最后改 API。原因：Agent 类依赖 prompt 文件存在。

### Prompt 搬运规则
- 从 DeepTutor 源文件复制后，只改 3 类内容：角色名、变量名、注释语言
- 保留原有的 system/user 分区结构、JSON schema、输出格式说明
- 每个文件加一行注释标注来源：`# 搬运自 DeepTutor: {源文件路径}`
- 变量名替换用上表"变量改名规则"

### Agent 类编写规则
- 继承 `app.agents.base_agent.BaseAgent`，参考 `profile_agent.py` 的结构
- `__init__` 中调用 `super().__init__(agent_name="xxx_agent")`，然后创建专用 LLM 实例
- `build_graph()` 返回 `StateGraph` 的 `.compile()`
- 节点方法命名：`_xxx_node(self, state: dict) -> dict`
- Mock 模式下 LLM 调用走 `SparkLLM(use_mock=True)` 的 mock 回复
- 所有 State 用 TypedDict 定义

### API 端点改造
- `internal_api.py` 的 4 个 endpoint 目前是硬编码 mock 数据
- 改成创建 Agent 实例 → `agent.run(state)` → SSE 流式输出
- 保留现有 SSE 格式：`data: {json}\n\n`，事件类型 token/progress/profile_update/done
- `/internal/exercise/generate` 是新建端点（目前不存在），需要新增
- Agent 单例模式：参考 `_get_profile_agent()` 的写法，每个 Agent 一个模块级单例

### 禁止事项
- 不要引入新依赖（websockets, httpx, langgraph, pyyaml 已够用）
- 不要新建 `prompts/snippets/` 文件（现有的 3 个够用）
- 不要修改 BaseAgent 的 `_load_prompt()` 行为
- ExerciseAgent 的 3 阶段不要拆成 3 个 Agent

### 测试时注意
- Windows 中文环境 curl 可能 GBK 编码问题，优先用 Python httpx 测试
- 数据库没有 aiomysql 时会降级到内存模式，不影响 Mock 测试
- 所有 Agent 的 use_mock_llm 默认 True

---

产出文件：.claude-loop/active/01-claude-plan.md | Round DAY03-001
