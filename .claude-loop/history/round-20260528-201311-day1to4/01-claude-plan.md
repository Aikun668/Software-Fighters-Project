# Claude 计划 | Round DAY04-001 | 2026-05-27

## 任务 ID
TASK-DAY04-001

## 任务类型
feature — 关闭 Mock，5 Agent 全部接入真实 Spark API

## 目标

把 `USE_MOCK_LLM=false`，5 个 Agent 从假数据切换到真实 LLM 驱动。

---

## 核心策略：搬理念，适配实现

关键认知：**我们的 LLM 基础设施和 DeepTutor 不同**。DeepTutor 用 OpenAI 兼容 API（`client.chat.completions.create`），我们用 Spark WebSocket API（`SparkLLM.chat`）。所以：

- **纯逻辑工具**可以直接搬代码（JSON 解析、容错策略）
- **LLM 调用模式**只能搬流程理念，具体实现必须适配 SparkLLM 的接口
- **和架构耦合的业务逻辑**不能硬搬（多轮代理循环、BlockContext 体系、exploration report 等）

### 搬什么、搬到什么程度

| 从哪 | 搬什么 | 搬法 | 注意 |
|------|--------|------|------|
| DeepTutor `json_parser.py` | JSON 三层容错策略 | **搬代码** — 纯逻辑，不依赖 LLM 接口 | ✅ 可以几乎原样搬 |
| DeepTutor `_llm_writer.py` llm_json() | "调LLM→解析→校验→重试→fallback" 流程 | **搬理念** — DeepTutor 内部调 `factory.complete()`（OpenAI），我们调 `SparkLLM.chat()`（WebSocket），实现完全不同 | ⚠️ 只搬流程思路，自己写代码 |
| DeepTutor `page_planner.py` _build_block() | 按 role 选子 prompt 模板逐块生成 | **搬理念** — DeepTutor 有完整的 BlockContext（book/chapter/page/exploration），我们只是"按 role 路由到不同 YAML prompt"，简单得多 | ⚠️ 不要搬 BlockContext 那套 |
| DeepTutor `spine_synthesizer.py` | draft→revise 两阶段路径生成 | **搬理念** — 深层的 `_call_json()` 调的是 `self.stream_llm()` + `response_format=json_object`，Spark 不支持 | ⚠️ 搬两阶段结构，不搬调用代码 |
| DeepTutor `pipeline.yaml` | 6 种题型的 JSON schema | **搬代码**（Day3 已搬）— 但 prompt 里的 THINK/TOOL/FINISH 多轮代理指令要砍 | ⚠️ 已搬的内容也需要修剪 |
| OpenMAIC SSE heartbeat | 长连接保活机制 | **搬理念** — OpenMAIC 是 TS ReadableStream，我们是 Python StreamingResponse，实现完全不同 | ⚠️ 可选，本次复杂度高就跳过 |

### 不搬什么

- **DeepTutor 的多轮代理循环**（THINK/TOOL/FINISH）— 我们是 LangGraph 单轮节点，硬搬架构冲突
- **DeepTutor 的异常层级体系**（7 种 LLMError 子类）— 我们只有一个 SparkLLM provider，`(ConnectionError, RuntimeError)` 够了
- **DeepTutor 的 LlamaIndex / tiktoken** — token 计数的依赖留给 ChromaDB 阶段
- **DeepTutor 的 BlockContext / ExplorationReport** — book engine 的上下文体系，我们的 ContentAgent 没有这个生命周期
- **DeepTutor 的 `response_format={"type": "json_object"}`** — Spark API 不支持结构化输出，prompt 里自然语言约束就行
- **OpenMAIC 的 Stream retry + abort 机制** — TS 的 AbortSignal 体系，Python asyncio 有自己的取消机制

---

## Phase A：基础设施 — 让 LLM 输出能被接住

Round 1 最大的风险不是 LLM 返回内容不好，是**LLM 返回了但代码接不住**。先统一 JSON 解析入口，修连接健壮性，配好开关。

### A1. 搬 DeepTutor JSON 三层容错：直接搬代码

**源**：`DeepTutor-参考版/deeptutor/utils/json_parser.py` → `parse_json_response()`

**搬法**：纯逻辑工具，可以直接搬。三层策略（markdown 提取 → 直接解析 → json_repair 修复）不依赖任何 DeepTutor 特定接口。我们的 venv 里已有 `json_repair`。

**做法**：新建 `app/utils/json_parser.py`，提供一个 `parse_llm_json(text, default)` 函数。5 个 Agent 的 JSON 解析统一入口。

**效果**：ProfileAgent 之前那个正则截断嵌套 JSON 的 bug 自然修掉（三层容错不依赖正则提取）。

### A2. BaseAgent 加 LLM→JSON 调用的轻量封装：搬理念

**源**：DeepTutor `_llm_writer.py` → `llm_json()` 和 `spine_synthesizer.py` → `_call_json()`

**搬法**：只搬流程概念——"加载 prompt → 填充变量 → 调 LLM → 解析 JSON → 校验关键字段 → 失败重试一次 → 兜底 fallback"。具体代码完全自写，因为我们的 LLM 调法是 `SparkLLM.chat(messages, system_prompt)` 而非 DeepTutor 的 `factory.complete()`。

**为什么值得封装**：接下来 ExerciseAgent 和 PathAgent 各有 2 个节点要接入 LLM，每个节点如果手写一遍"加载 → 调 LLM → 解析 → 校验 → fallback"就是 4 遍重复代码。

**做法**：BaseAgent 新增 `_call_llm_json()` 方法，语义上做这些事：
1. 从 YAML 加载 system 和 user 两部分 prompt
2. 用传入的 variables 做 `interpolate_variables()` 插值
3. 调 `self.llm.chat()`（非流式，结构化输出场景）
4. 调 `parse_llm_json()` 解析结果
5. 检查结果中是否有 expected_key → 有就返回；没有就重试一次
6. 仍失败返回 fallback

**不侵入现有代码**：ProfileAgent 和 TutorAgent 已稳定的调用链不动。新方法只给 ExerciseAgent / PathAgent / ContentAgent 的 generate 节点用。

### A3. SparkLLM 连接健壮性

**问题**：`chat()` 没有连接超时，TCP 挂起永久阻塞。`chat_stream()` 只 catch `ConnectionClosed`，OSError（DNS 失败/拒绝连接）和 asyncio.TimeoutError 直接炸穿。

**做法**：WebSocket connect 加 `open_timeout=30s`，消息接收循环外包 `asyncio.timeout(120s)`。`chat_stream()` 的异常捕获补上 `OSError` 和 `asyncio.TimeoutError`，统一转 `RuntimeError` 向上抛（Agent 层的 try/except 能接住）。

### A4. 环境变量

`.env` 补 `USE_MOCK_LLM=false`。改回 `true` 即切回 Mock 模式，开发调试不受影响。

---

## Phase B：三个已有 LLM 调用链的 Agent 切真实

这三个 Agent Day3 就写好了 LLM 调用代码（用的是 `self.llm.chat()` 和 `self.llm.chat_stream()`），但因为 Mock 模式从来没真正跑过。Phase B 关闭 Mock 后验证它们的 prompt 和调用链。

### B1. ProfileAgent

**现状**：extract 节点调 `extract_llm.chat()` 提取画像，response 节点调 `response_llm.chat_stream()` 生成回复。两条链都写好了。

**切真实后要验证的**：
- extract 节点的 `_parse_extract_result()` 已切换到 A1 的 `parse_llm_json()`（修了嵌套 JSON 截断的 bug）
- 画像提取质量：真实 LLM 能否从对话中正确识别 knowledge_base / weak_points / interest_direction 等维度
- 流式回复中文正常

**不动**：StateGraph 拓扑、prompt 文件、API 端点。

### B2. TutorAgent

**现状**：retrieve → respond 两节点。retrieve 返回硬编码知识（TODO: ChromaDB），respond 调 `self.llm.chat_stream()` 生成回复。

**切真实后要验证的**：
- 流式 SSE 中文输出正常（无 `\uXXXX` 转义）
- prompt 中 `{student_profile}` + `{knowledge_context}` 注入生效
- 即使 knowledge_context 还是硬编码文本，LLM 回复也应比 mock 更自然

**不动**：Agent 代码、prompt 文件、API 端点。远期等 ChromaDB 阶段再改 retrieve 节点。

### B3. ContentAgent

**现状**：plan 节点调 `plan_llm.chat()` 生成 outline JSON。generate 节点是纯 mock（硬编码 5 个 content block）。

**切真实后的改动**：generate 节点需要加 LLM 调用。

**业务逻辑**：plan 产出的 outline 包含 `subsections` 数组（每项：heading、role、focus）。generate 节点遍历 subsections，根据 role 选子 prompt 模板调 LLM：
- role = `example` → 用 code.yaml 的 prompt 生成代码案例
- role = `comparison/application` → 用 deep_dive.yaml 生成拓展材料
- role = `core/derivation` → 用默认 section prompt 生成讲解文本

每块独立调 LLM，失败时有 fallback。collect 结果组成 content_blocks 返回。

**借鉴**：DeepTutor `SectionArchitect._build_block()` —— 每个 block 按类型路由到不同的 Generator，Generator 从 BlockContext 取 chapter 级别参数 + block 自身参数。

**不动**：StateGraph 拓扑（plan → generate）、API 端点。

---

## Phase C：两个零 LLM 调用的 Agent 全新接入

这两个 Agent 当前所有节点都是纯 Python 造假数据，没有任何 LLM 调用。Phase C 给每个节点接入 LLM，用 Phase A 搬过来的 `_call_llm_json()` 方法。

### C1. ExerciseAgent — 搬 DeepTutor 出题流水线

**当前**：plan 节点 for 循环造固定模板。generate 节点 if/else 造假题目文本。零 LLM。

**目标**：plan 节点调 LLM 产题型蓝图 → generate 节点逐题调 LLM 产完整题目。

**关键问题：pipeline.yaml prompt 不匹配**

DeepTutor 的出题系统是多轮代理循环（explore → THINK → TOOL → FINISH），而我们是单轮 LangGraph 节点。`pipeline.yaml` 里的工具调用协议指令必须砍掉，否则 LLM 会输出工具指令而非 JSON 题目。

**做法**：
- 修改 `pipeline.yaml`：删 THINK/TOOL/FINISH 协议段落，保留 6 种题型的 JSON schema 和角色定义，加"请直接输出 JSON"指令
- `_plan_node`：用 `_call_llm_json()` 调 plan_system/plan_user prompt → 解析出题型蓝图 → 失败则 fallback 原 mock 逻辑
- `_generate_node`：遍历蓝图，用 `_call_llm_json()` 逐题调 quiz_system/quiz_user prompt → 每道题有完整题干+选项+答案+解析 → 失败单题有 mock fallback
- `_review_node`：保持纯逻辑不变（只拼 response 字符串）

**借鉴**：DeepTutor `question_agent.py` 的 prompt 调用模式——`get_prompt("plan_system")` + `get_prompt("plan_user")` → LLM → 解析。但我们用 A2 搬过来的 `_call_llm_json()`，更简洁。

### C2. PathAgent — 搬 DeepTutor spine_synthesizer

**当前**：draft 节点 3 个 if/else 分支（按 knowledge_base 值）选硬编码步骤。revise 节点子串匹配标 interest。零 LLM。

**目标**：draft 节点调 LLM 生成 concept_graph + steps → revise 节点调 LLM 检查并修正。

**简化决策**：DeepTutor 的 SpineSynthesizer 是 draft → critique → revise 三轮。我们合并为 draft → revise 两轮——revise 的 prompt 中内嵌自我审查指令（"请检查路径的覆盖度、顺序合理性、与画像的匹配度"），省一次 API 调用达到类似效果。

**做法**：
- `_draft_node`：用 `_call_llm_json()` 调 system.yaml 的 system/user_template → 解析 concept_graph + steps → 失败 fallback 原有 if/else 逻辑
- `_revise_node`：用 `_call_llm_json()` 调 path_planner.yaml 的 system/user_template → 解析修正后的 steps → 失败 fallback 原有兴趣匹配逻辑

**借鉴**：DeepTutor `spine_synthesizer.py` 的 `_call_json(system, user, stage)` 模式——我们 A2 搬的就是它。

---

## 关键决策

| 决策 | 选了什么 | 为什么 |
|------|---------|--------|
| JSON 解析入口 | 新建 `parse_llm_json()` 统一函数 | 5 个 Agent 都要用，不能各写各的 |
| LLM 调用封装 | BaseAgent 新增 `_call_llm_json()` | 省掉每个 Agent 手写"调LLM→解析→校验→fallback"的重复代码 |
| ExerciseAgent prompt | 砍工具协议，留 JSON schema | 架构不同，多轮代理 vs 单轮节点，硬搬会坏 |
| PathAgent 轮次 | draft→revise 两轮 | 少一次 API 调用，revise 内嵌自检指令 |
| 错误处理 | 每个节点 fallback 回原 mock 逻辑 | Mock 模式向后兼容，真实环境失败不崩溃 |
| 超时 | connect=30s, 整体=120s | 星火 4.0 Ultra 通常 5-15s 返回 |

---

## 文件变更清单

| 文件 | 操作 | 搬自 |
|------|------|------|
| `app/utils/json_parser.py` | **新建** | DeepTutor `utils/json_parser.py` |
| `app/agents/base_agent.py` | 修改（新增 `_call_llm_json`） | DeepTutor `_llm_writer.py` + `spine_synthesizer.py` |
| `app/services/llm_service.py` | 修改（超时+异常） | DeepTutor provider timeout 模式 |
| `.env` | 修改（加开关） | — |
| `app/agents/profile_agent.py` | 修改（换 JSON 解析） | — |
| `app/agents/content_agent.py` | 修改（generate 加 LLM） | DeepTutor `page_planner.py` |
| `app/agents/exercise_agent.py` | 重写 | DeepTutor `question_agent.py` |
| `app/agents/path_agent.py` | 重写 | DeepTutor `spine_synthesizer.py` |
| `prompts/exercise_agent/pipeline.yaml` | 修改（砍工具指令） | — |

**不改**：TutorAgent、internal_api.py、prompt_loader.py、其余 prompt YAML、StateGraph 拓扑、SSE 端点结构

---

## 验收标准

- [ ] `parse_llm_json()` 能处理三种格式：正常 JSON、markdown 包裹的 JSON、json_repair 可修复的残缺 JSON
- [ ] `_call_llm_json()` 封装可用——ExerciseAgent 和 PathAgent 的新节点用它实现
- [ ] SparkLLM 连接 30s 超时、整体 120s 超时生效
- [ ] Profile / Tutor / Content 切真实 LLM 后返回 LLM 生成的内容（非 mock 硬编码）
- [ ] Exercise / Path 全新接入 LLM 后 plan/generate/draft/revise 均由 LLM 驱动
- [ ] `python test_spark_api.py` 通过
- [ ] `USE_MOCK_LLM=true` 改回 mock 模式仍可跑（向后兼容）
- [ ] 5 个端点 SSE / JSON 返回均为真实 LLM 产出

## 验证

```bash
# 0. Spark API 仍通
python test_spark_api.py

# 1. JSON 解析器独立验证
python -c "from app.utils.json_parser import parse_llm_json; \
  print(parse_llm_json('{\"a\":{\"b\":1}}')); \
  print(parse_llm_json('\`\`\`json\n{\"x\":1}\n\`\`\`')); \
  print(parse_llm_json('{\"key\":\"val\"'))"

# 2-6. 启动服务后逐端验证 Profile/Tutor/Content/Exercise/Path
# 每个端检查返回内容已从 mock 硬编码变为 LLM 生成
```

---

产出文件：.claude-loop/active/01-claude-plan.md | Round DAY04-001
