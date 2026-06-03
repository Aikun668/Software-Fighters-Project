# Claude 计划 | Round DAY04-001 | 2026-05-27

## 任务 ID
TASK-DAY04-001

## 任务类型
feature（真实 LLM 全线打通）

## 目标
关闭 Mock 模式，5 个 Agent 全部接入真实 Spark API。Phase A 修基础设施（4 个必须先修的 bug），Phase B 切已有 LLM 的三 Agent，Phase C 给无 LLM 的二 Agent 全新接入。

## 背景

Day 3 搭好了 5 Agent 骨架，全部 Mock 模式可跑。当前状态：

| Agent | LLM 调用已有？ | 需要做什么 |
|-------|---------------|-----------|
| ProfileAgent | ✅ extract_llm.chat() + response_llm.chat_stream() | 修 JSON 解析 bug |
| TutorAgent | ✅ self.llm.chat_stream() | 改配置即可 |
| ContentAgent | ⚠️ _plan_node 有，_generate_node 纯 mock | plan 已有，generate 加 LLM |
| ExerciseAgent | 🔴 零 LLM 调用 | 全新接入 |
| PathAgent | 🔴 零 LLM 调用 | 全新接入 |

**扫描发现的 4 个必须先修的 bug**（否则直接切真实 LLM 会炸）：
1. ProfileAgent 的 `_parse_extract_result()` 正则 `\{[\s\S]*?\}` 懒惰匹配，遇到嵌套 JSON 就截断
2. SparkLLM 的 `chat()` / `chat_stream()` 没超时，星火卡住永久挂起
3. `chat_stream()` 只 catch `ConnectionClosed`，DNS 失败/连接拒绝的 `OSError` 直接炸穿
4. `.env` 没有 `USE_MOCK_LLM=false`（API 层工厂函数默认 true，会覆盖 Agent 构造参数）

**参考项目位置**：
- `D:\My_Grand_Projects2026\Software-Cup-Game2026\DeepTutor-参考版\deeptutor\`（prompt + 调用模式源）
- `D:\My_Grand_Projects2026\Software-Cup-Game2026\OpenMAIC-参考版\`（SSE 流模式源）
- `D:\My_Grand_Projects2026\Software-Cup-Game2026\Software-Fighters-Project\ai-service\`（目标项目）

---

## 验收标准
- [ ] Phase A：4 个基础设施 bug 全部修复
- [ ] Phase B：Profile / Tutor / Content 三个 Agent 真实 LLM 返回合理内容
- [ ] Phase C：Exercise / Path 两个 Agent 接入 LLM 并返回合理内容
- [ ] `python test_spark_api.py` 全部通过（无回归）
- [ ] 5 个端点 SSE 流中全是真实 LLM 生成内容（非 mock 硬编码）
- [ ] JSON 解析容错：LLM 返回的 markdown 包裹 / 残缺 JSON 能正确 fallback

---

## Phase A：基础设施加固（必须先修，4 项）

### A1. 修复 ProfileAgent JSON 解析 — 搬 DeepTutor 3 层容错

**问题**：`app/agents/profile_agent.py` 的 `_parse_extract_result()` 方法（line 249-274）。正则 `\{[\s\S]*?\}` 是懒惰匹配，嵌套 JSON `{"updates": {"knowledge_base": 30}}` 会在第一个 `}` 处截断：
```
输入:  {"updates": {"knowledge_base": 30, "learning_goal": "test"}}
匹配:  {"updates": {"knowledge_base": 30, "learning_goal": "test"}   ← 丢了 }
结果:  json.loads 失败 → fragment = {} → 画像永远不更新
```

**借鉴来源**：DeepTutor `deeptutor/utils/json_parser.py` 的 `parse_json_response()` 函数

**做法**：新建 `app/utils/json_parser.py`，搬 DeepTutor 的 3 层容错逻辑：

```python
# app/utils/json_parser.py
import json
import re
import logging

logger = logging.getLogger(__name__)

def parse_llm_json(text: str, default=None):
    """
    借鉴 DeepTutor parse_json_response() 的 3 层容错：
    Tier 1: 提取 ```json...``` markdown 代码块
    Tier 2: 直接 json.loads()
    Tier 3: json_repair 修复后 json.loads()
    """
    if default is None:
        default = {}

    text = text.strip()

    # Tier 1: 提取 markdown 代码块
    code_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if code_match:
        text = code_match.group(1).strip()

    # Tier 2: 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Tier 2.5: 正则提取第一个完整 {...}（非懒惰，匹配到末尾配对）
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group())
        except json.JSONDecodeError:
            pass

    # Tier 3: json_repair 修复
    try:
        from json_repair import repair_json
        repaired = repair_json(text)
        return json.loads(repaired)
    except Exception:
        pass

    logger.warning(f"parse_llm_json failed for: {text[:200]}")
    return default
```

然后修改 `profile_agent.py` 的 `_parse_extract_result()`，用 `parse_llm_json()` 替代原有的嵌套 try/except：

```python
# profile_agent.py _parse_extract_result() 改为：
def _parse_extract_result(self, text: str) -> dict:
    from app.utils.json_parser import parse_llm_json
    data = parse_llm_json(text, default={"updates": {}})
    updates = data.get("updates", data)
    return {k: v for k, v in updates.items() if k in DIMENSIONS}
```

### A2. SparkLLM 加超时 + 完善异常覆盖

**文件**：`app/services/llm_service.py`

**修改 1** — `chat()` 方法（line 134）：`websockets.connect()` 加 `open_timeout=30`：

```python
# 改前：
async with websockets.connect(ws_url, max_size=10 * 1024 * 1024) as ws:

# 改后：
async with websockets.connect(ws_url, max_size=10 * 1024 * 1024, open_timeout=30) as ws:
```

**修改 2** — `chat()` 方法：消息接收循环加 `asyncio.wait_for()` 整体超时（120s）：

```python
# 在 async for raw in ws: 循环外包一层
try:
    async with asyncio.timeout(120):
        async for raw in ws:
            ...
except asyncio.TimeoutError:
    raise RuntimeError("Spark API request timed out after 120s")
```

**修改 3** — `chat_stream()` 方法（line 175）：异常捕获从单独的 `websockets.ConnectionClosed` 扩展为也覆盖 `OSError` 和 `asyncio.TimeoutError`：

```python
# 改前：
except websockets.ConnectionClosed as e:
    raise RuntimeError(f"WebSocket connection closed: {e}")

# 改后：
except (websockets.ConnectionClosed, OSError, asyncio.TimeoutError) as e:
    raise RuntimeError(f"Spark API connection error: {e}")
```

**文件顶部加 import**：`import asyncio`

### A3. `.env` 加 `USE_MOCK_LLM=false`

**文件**：`.env`

在文件末尾追加一行：
```
USE_MOCK_LLM=false
```

**说明**：`internal_api.py` 的 5 个工厂函数都读 `os.getenv("USE_MOCK_LLM", "true")`，默认 true。不加这行就算 Agent 构造传了 `use_mock=false` 也会被覆盖回 mock。切回 mock 只需改回 `true`。

### A4. 全部 Agent 的 JSON 解析统一用 `parse_llm_json`

**文件**：`app/agents/content_agent.py` `_plan_node`（line 98）

将 `json.loads(result)` 改为 `parse_llm_json(result)`，配合已有的结构校验（line 100-101）：

```python
# 改前：
outline = json.loads(result)

# 改后：
from app.utils.json_parser import parse_llm_json
outline = parse_llm_json(result, default={})
```

同样，后续 Phase C 的 ExerciseAgent 和 PathAgent 都用 `parse_llm_json()` 而非裸 `json.loads()`。

---

## Phase B：已有 LLM 的三 Agent 切真实

### B1. ProfileAgent 切真实 LLM

**文件**：`app/agents/profile_agent.py`

无需改代码（Phase A1 已修 JSON 解析）。只需确认 `internal_api.py` 从 `.env` 读到 `USE_MOCK_LLM=false`，工厂函数创建 Agent 时 `use_mock=False`。

**验证重点**：extract 节点能正确解析嵌套 JSON 画像。关键场景——学生说"我数学基础不好，想学深度学习"，画像应更新 `weak_points: ["数学基础薄弱"]` + `interest_direction: ["深度学习"]`。

### B2. TutorAgent 切真实 LLM

**文件**：无需改代码。`self.llm.chat_stream()` 已就绪。

**OpenMAIC 借鉴**：`internal_api.py` 的 SST 生成器加心跳注释帧（防止 LLM 长耗时期间代理断开）：

在 `tutor_chat` 的 `event_stream()` 开头加：
```python
import asyncio
# 每 15 秒发一次心跳注释帧
async def heartbeat():
    while True:
        await asyncio.sleep(15)
        yield f":heartbeat\n\n"
```

如果实现复杂可以跳过，当前先用 `chat_stream` 自带的 token 级推送保持连接活跃。

**验证重点**：流式中文明文无 `\uXXXX` 转义，prompt 中的 `{student_profile}` + `{knowledge_context}` 变量注入生效。

### B3. ContentAgent 切真实 LLM + generate 节点加 LLM 调用

**文件**：`app/agents/content_agent.py`

**现状**：`_plan_node` 已有 `self.plan_llm.chat()` 调用。`_generate_node` 纯 mock 返回硬编码 content_blocks。

**改法** — `_generate_node` 不再硬编码，改为按 outline.subsections 逐块调 LLM：

```python
async def _generate_node(self, state: ContentState) -> dict:
    """按 outline.subsections 逐块调用 LLM 生成内容"""
    topic = state.get("topic", "")
    outline = state.get("outline", {})
    subsections = outline.get("subsections", [])
    intro = outline.get("intro", f"{topic}介绍")

    content_blocks = []

    # 1. intro block（直接用 outline 的 intro 文本）
    content_blocks.append({
        "type": "section", "heading": "概述", "content": intro,
    })

    # 2. 每个 subsection 调一次 LLM（借鉴 DeepTutor _build_block）
    for i, sub in enumerate(subsections):
        heading = sub.get("heading", f"第{i+1}节")
        role = sub.get("role", "core")

        # 按 role 选对应的子 prompt
        if role == "example":
            filename, key_name = "code.yaml", "system"
        elif role in ("comparison", "application"):
            filename, key_name = "deep_dive.yaml", "system"
        else:
            # core / derivation → 通用 section 生成
            filename, key_name = "outline.yaml", "system"  # 复用 outline system prompt

        sub_system = self._load_extra_prompt(filename=filename, key=key_name)
        sub_user = self._load_extra_prompt(filename=filename, key="user_template")
        sub_user_filled = interpolate_variables(sub_user, {
            "topic": sub.get("focus", topic),
            "topic_summary": f"{heading} - {sub.get('focus', '')}",
            "objectives": outline.get("key_takeaway", ""),
            "student_profile": self._format_profile(state.get("student_profile", {})),
        })

        try:
            result = await self.llm.chat(
                [{"role": "user", "content": sub_user_filled}],
                system_prompt=sub_system,
            )
            content = result.strip()
        except (ConnectionError, RuntimeError) as e:
            logger.error(f"Generate block {i} failed: {e}")
            content = f"## {heading}\n\n本节讲解{sub.get('focus', topic)}的核心知识。\n\n（内容生成失败，请稍后重试）"

        content_blocks.append({
            "type": "code" if role == "example" else "callout" if role in ("comparison", "application") else "section",
            "heading": heading,
            "content": content,
        })

    # 3. 末尾追加 key_takeaway
    key_takeaway = outline.get("key_takeaway", f"掌握{topic}的核心原理。")
    content_blocks.append({
        "type": "callout", "heading": "关键要点", "content": key_takeaway,
    })

    response = f"已为您生成「{topic}」的学习内容，共 {len(content_blocks)} 个内容块。"
    return {"content_blocks": content_blocks, "response": response, "stage": "generated"}
```

**注意**：当 `USE_MOCK_LLM=true` 时也能正常工作（Mock 返回 hardcoded 文本），保持向后兼容。

---

## Phase C：零 LLM 的二 Agent 全新接入

### C1. ExerciseAgent — 搬 DeepTutor question pipeline

**借鉴来源**：`DeepTutor-参考版/deeptutor/agents/question/question_agent.py` 的 LLM 调用模式

**文件**：`app/agents/exercise_agent.py`

**现状**：`_plan_node` 和 `_generate_node` 是纯 Python mock 逻辑，不调 LLM。

**关键前提**：当前 `pipeline.yaml` 的 prompt 是从 DeepTutor 完整搬过来的，含有 THINK / TOOL / FINISH 多轮代理协议。但 ExerciseAgent 是简单的 3 节点 LangGraph 单轮调用。需要**简化 prompt**——砍掉工具调用指令，保留题型 JSON schema。

**第一步** — 修改 `prompts/exercise_agent/pipeline.yaml`：

`plan_system` 和 `plan_user` 保持角色定义 + 题型规则，但删除 `THINK/TOOL/FINISH` 协议相关的指令。改为直接输出 JSON 蓝图的指令。

`quiz_system` 和 `quiz_user` 保留 6 种题型的 JSON schema，但删除工具调用格式，改为"请直接输出 JSON"。

（Builder 自行判断具体砍哪些行——核心原则：保留 JSON schema 和变量名，删除多轮代理指令。）

**第二步** — 修改 `_plan_node`：

```python
async def _plan_node(self, state: ExerciseState) -> dict:
    topic = state.get("topic", "")
    count = state.get("count", 3)
    difficulty = state.get("difficulty", "medium")
    student_profile = state.get("student_profile", {})

    plan_system = self._load_extra_prompt(filename="pipeline.yaml", key="plan_system")
    plan_user = self._load_extra_prompt(filename="pipeline.yaml", key="plan_user")
    user_filled = interpolate_variables(plan_user, {
        "topic": topic,
        "count": str(count),
        "difficulty": difficulty,
        "weak_points": ", ".join(student_profile.get("weak_points", [])),
    })

    try:
        result = await self.plan_llm.chat(
            [{"role": "user", "content": user_filled}],
            system_prompt=plan_system,
        )
        from app.utils.json_parser import parse_llm_json
        plan_data = parse_llm_json(result, default={"templates": []})
        plan = plan_data.get("templates", [])
        if not plan:
            raise ValueError("Empty plan from LLM")
    except (json.JSONDecodeError, ValueError, ConnectionError, RuntimeError) as e:
        logger.error(f"Exercise plan failed: {e}")
        # fallback: 简单的 alternating plan
        plan = [
            {"question_id": f"q_{i+1}", "topic": topic,
             "question_type": "choice" if i % 2 == 0 else "short_answer",
             "difficulty": difficulty}
            for i in range(count)
        ]

    return {"plan": plan, "stage": "planned"}
```

**第三步** — 修改 `_generate_node`：

```python
async def _generate_node(self, state: ExerciseState) -> dict:
    plan = state.get("plan", [])
    questions = []

    quiz_system = self._load_extra_prompt(filename="pipeline.yaml", key="quiz_system")
    quiz_user_tmpl = self._load_extra_prompt(filename="pipeline.yaml", key="quiz_user")

    for item in plan:
        user_filled = interpolate_variables(quiz_user_tmpl, {
            "question_id": item.get("question_id", ""),
            "question_type": item.get("question_type", "choice"),
            "topic": item.get("topic", ""),
            "difficulty": item.get("difficulty", "medium"),
        })

        try:
            result = await self.plan_llm.chat(
                [{"role": "user", "content": user_filled}],
                system_prompt=quiz_system,
            )
            from app.utils.json_parser import parse_llm_json
            question = parse_llm_json(result, default={})
            if not question:
                raise ValueError("Empty question from LLM")
        except (json.JSONDecodeError, ValueError, ConnectionError, RuntimeError) as e:
            logger.error(f"Exercise generate {item.get('question_id')} failed: {e}")
            question = {
                "question_type": item.get("question_type", "choice"),
                "question": f"关于{item.get('topic', '')}，以下哪项描述是正确的？",
                "options": {"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"},
                "correct_answer": "A",
                "explanation": "默认解析。",
            }

        questions.append(question)

    return {"questions": questions, "stage": "generated"}
```

`_review_node` 保持纯逻辑不调 LLM（不变）。

### C2. PathAgent — 搬 DeepTutor spine_synthesizer

**借鉴来源**：`DeepTutor-参考版/deeptutor/book/agents/spine_synthesizer.py` 的 `_call_json()` + draft→revise 模式

**文件**：`app/agents/path_agent.py`

**现状**：`_draft_node` 和 `_revise_node` 是纯 Python mock 逻辑。

**改法**：

```python
async def _draft_node(self, state: PathState) -> dict:
    """Draft：LLM 生成初始路径"""
    student_profile = state.get("student_profile", {})

    draft_system = self._load_extra_prompt(filename="system.yaml", key="system")
    draft_user = self._load_extra_prompt(filename="system.yaml", key="user_template")
    user_filled = interpolate_variables(draft_user, {
        "student_profile": self._format_profile(student_profile),
    })

    try:
        result = await self.path_llm.chat(
            [{"role": "user", "content": user_filled}],
            system_prompt=draft_system,
        )
        from app.utils.json_parser import parse_llm_json
        data = parse_llm_json(result, default={})
        concept_graph = data.get("concept_graph", {})
        steps = data.get("steps", [])
    except (json.JSONDecodeError, ValueError, ConnectionError, RuntimeError) as e:
        logger.error(f"Path draft failed: {e}")
        # fallback: 保留原 mock 逻辑
        knowledge_base = student_profile.get("knowledge_base", 0)
        if knowledge_base < 30:
            steps = [
                {"order": 1, "topic": "Python 基础回顾", "status": "pending", "resource_id": None},
                {"order": 2, "topic": "人工智能概述", "status": "pending", "resource_id": None},
                {"order": 3, "topic": "机器学习基础", "status": "pending", "resource_id": None},
            ]
        elif knowledge_base < 60:
            steps = [
                {"order": 1, "topic": "机器学习算法深入", "status": "pending", "resource_id": None},
                {"order": 2, "topic": "神经网络基础", "status": "pending", "resource_id": None},
                {"order": 3, "topic": "深度学习实践", "status": "pending", "resource_id": None},
            ]
        else:
            steps = [
                {"order": 1, "topic": "Transformer 架构", "status": "pending", "resource_id": None},
                {"order": 2, "topic": "大模型微调", "status": "pending", "resource_id": None},
                {"order": 3, "topic": "多模态应用", "status": "pending", "resource_id": None},
            ]
        steps.extend([
            {"order": 4, "topic": "项目实战", "status": "pending", "resource_id": None},
            {"order": 5, "topic": "前沿探索", "status": "pending", "resource_id": None},
        ])
        concept_graph = {"nodes": [], "edges": []}

    return {"concept_graph": concept_graph, "steps": steps, "version": 1}
```

```python
async def _revise_node(self, state: PathState) -> dict:
    """Revise：LLM 根据画像检查并修正路径"""
    steps = state.get("steps", [])
    student_profile = state.get("student_profile", {})

    revise_system = self._load_extra_prompt(filename="path_planner.yaml", key="system")
    revise_user = self._load_extra_prompt(filename="path_planner.yaml", key="user_template")
    user_filled = interpolate_variables(revise_user, {
        "student_profile": self._format_profile(student_profile),
    })

    try:
        result = await self.path_llm.chat(
            [{"role": "user", "content": user_filled}],
            system_prompt=revise_system,
        )
        from app.utils.json_parser import parse_llm_json
        data = parse_llm_json(result, default={})
        revised_steps = data.get("steps", [])
        if revised_steps:
            steps = revised_steps
    except (json.JSONDecodeError, ValueError, ConnectionError, RuntimeError) as e:
        logger.error(f"Path revise failed: {e}")
        # fallback: 保留原 mock 逻辑 — 兴趣匹配标注
        interest = student_profile.get("interest_direction", [])
        if interest:
            steps = [
                {**step, "status": "recommended" if any(i in step["topic"] for i in interest) else step.get("status", "pending")}
                for step in steps
            ]

    response = f"已为您规划 {len(steps)} 步学习路径。"
    return {"steps": steps, "response": response, "version": 2}
```

**新增 `_format_profile` 方法**（与 ContentAgent / TutorAgent 保持一致，后续可提取为公共工具）：

```python
def _format_profile(self, profile: dict) -> str:
    if not profile:
        return "（暂无学生画像，按默认难度规划）"
    lines = ["学生画像："]
    labels = {
        "knowledge_base": "知识基础",
        "cognitive_style": "学习风格",
        "learning_goal": "学习目标",
        "weak_points": "薄弱环节",
        "learning_pace": "学习节奏",
        "interest_direction": "兴趣方向",
    }
    for key, label in labels.items():
        val = profile.get(key)
        if val is not None and val != []:
            if isinstance(val, list):
                val = "、".join(str(v) for v in val)
            elif key == "knowledge_base":
                val = f"{val}/100"
            lines.append(f"  - {label}: {val}")
    return "\n".join(lines) if len(lines) > 1 else "（暂无学生画像，按默认难度规划）"
```

---

## 借鉴对齐总表

| 搬什么 | 源文件（DeepTutor） | 目标文件（ai-service） | 搬什么逻辑 |
|--------|---------------------|----------------------|-----------|
| JSON 3 层容错 | `utils/json_parser.py` `parse_json_response()` | `app/utils/json_parser.py` `parse_llm_json()` | markdown提取→直接解析→json_repair修复 |
| LLM 超时 + 异常 | OpenAI 调用的 retry + timeout 模式 | `app/services/llm_service.py` | open_timeout + except OSError/TimeoutError |
| 逐块内容生成 | `book/agents/page_planner.py` `_build_block()` | `app/agents/content_agent.py` `_generate_node` | 按 subsection 选子 prompt 调 LLM |
| 出题 pipeline | `agents/question/` LLM 调用模式 | `app/agents/exercise_agent.py` | plan_system/user → LLM → 解析蓝图 → quiz_system/user → LLM → 逐题生成 |
| 路径 draft/revise | `book/agents/spine_synthesizer.py` `_call_json()` | `app/agents/path_agent.py` | system+user → LLM → parse_llm_json → dict |
| SSE 心跳 | **OpenMAIC** `scene-outlines-stream/route.ts` | `internal_api.py`（可选） | 15s 间隔注释帧防代理断开 |

---

## 修改文件清单（9 个）

| 文件 | 操作 | 阶段 |
|------|------|------|
| `app/utils/json_parser.py` | **新建** | A1 |
| `app/agents/profile_agent.py` | 修改（_parse_extract_result 改用 parse_llm_json） | A1 |
| `app/services/llm_service.py` | 修改（加超时 + OSError 捕获） | A2 |
| `.env` | 修改（加 USE_MOCK_LLM=false） | A3 |
| `app/agents/content_agent.py` | 修改（_generate_node 加 LLM 调用 + parse_llm_json） | A4, B3 |
| `app/agents/exercise_agent.py` | 重写（_plan_node + _generate_node 接入 LLM） | C1 |
| `app/agents/path_agent.py` | 重写（_draft_node + _revise_node 接入 LLM + _format_profile） | C2 |
| `prompts/exercise_agent/pipeline.yaml` | 修改（砍掉 THINK/TOOL/FINISH 多轮协议） | C1 |

**不改的文件**：
- `app/agents/tutor_agent.py` — 已就绪，只靠配置切真实
- `internal_api.py` — 已就绪
- `app/agents/base_agent.py` — 接口不变
- 其余 prompt YAML 文件

---

## 执行顺序

```
1. A1 新建 app/utils/json_parser.py（独立文件，无依赖）
2. A2 修改 llm_service.py（超时 + 异常）
3. A3 修改 .env（一行）
4. A4 + A1 修改 profile_agent.py（改用 parse_llm_json）
5. B1 验证 ProfileAgent 切真实
6. B2 验证 TutorAgent 切真实（改配置即可）
7. B3 修改 content_agent.py（_generate_node + parse_llm_json）
8. C1 修改 pipeline.yaml + exercise_agent.py（最大改动量）
9. C2 修改 path_agent.py
10. 全量验证（5 端点 + test_spark_api.py）
```

## 验证方式

```bash
# 0. 前置验证
cd ai-service && python test_spark_api.py
# 预期：3/3 passed

# 1. 模块导入
python -c "
from app.agents.tutor_agent import TutorAgent
from app.agents.content_agent import ContentAgent
from app.agents.exercise_agent import ExerciseAgent
from app.agents.path_agent import PathAgent
from app.agents.profile_agent import ProfileAgent
from app.utils.json_parser import parse_llm_json
print('All imports OK')
"

# 2. JSON 解析器单元测试
python -c "
from app.utils.json_parser import parse_llm_json
# 测试嵌套 JSON
result = parse_llm_json('{\"updates\": {\"knowledge_base\": 30, \"weak_points\": [\"math\"]}}')
print('nested:', result)
# 测试 markdown 包裹
result = parse_llm_json('\`\`\`json\n{\"key\": \"val\"}\n\`\`\`')
print('markdown:', result)
# 测试残缺 JSON（json_repair）
result = parse_llm_json('{\"key\": \"val\"')  # 缺 }
print('broken:', result)
"

# 3. 启动服务
# venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8001

# 4. Profile — 画像提取（重点：嵌套 JSON 解析）
curl -s -X POST http://localhost:8001/internal/profile/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":1, "messages":[{"role":"user","content":"我数学基础不好，想学深度学习"}]}'
# 预期：SSE 中有 profile_update 事件，weak_points 含数学相关，interest_direction 含深度学习

# 5. Tutor — 答疑
curl -s -X POST http://localhost:8001/internal/tutor/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":1, "messages":[{"role":"user","content":"什么是CNN？"}]}'
# 预期：流式中文，无 \uXXXX 转义

# 6. Content — 内容生成
curl -s -X POST http://localhost:8001/internal/resources/generate \
  -H "Content-Type: application/json" \
  -d '{"student_id":"1", "topic":"梯度下降"}'
# 预期：done 事件带 content_blocks，每块由 LLM 生成

# 7. Exercise — 出题
curl -s -X POST http://localhost:8001/internal/exercise/generate \
  -H "Content-Type: application/json" \
  -d '{"topic":"决策树", "count":3, "difficulty":"medium"}'
# 预期：done 事件带 questions 数组，题目含 LLM 生成的具体内容

# 8. Path — 学习路径
curl -s http://localhost:8001/internal/path/1
# 预期：steps 数组 + concept_graph 由 LLM 生成

# 9. 切回 Mock 验证（可选）
# 改 .env: USE_MOCK_LLM=true → 重启 → 所有端点仍正常返回 mock 数据
```

---

## 给 Builder 的注意事项

### Prompt 简化原则（ExerciseAgent pipeline.yaml）
- **删除**：THINK / TOOL / FINISH / ACTION 等多轮代理协议指令
- **保留**：6 种题型的 JSON schema（choice / concept / fill_in_blank / short_answer / written / coding）
- **保留**：角色定义、变量名（`{topic}` / `{count}` / `{difficulty}` / `{weak_points}` / `{question_id}` / `{question_type}`）
- **新增**："请直接输出 JSON，不要添加额外说明"

### JSON 解析统一原则
- 所有 LLM 输出解析**必须用 `parse_llm_json()`**，不能裸用 `json.loads()`
- `parse_llm_json` 位于 `app/utils/json_parser.py`（Phase A1 新建）

### 错误处理原则
- 所有 LLM 调用节点必须 try/except `(json.JSONDecodeError, ValueError, ConnectionError, RuntimeError)` 
- fallback 保留原有的 mock 逻辑（向后兼容，`USE_MOCK_LLM=true` 时仍能跑）
- Agent 构造函数的 `use_mock_llm` 参数保留（不做破坏性变更）

### 禁止事项
- 不要改 `BaseAgent`、`SparkLLM.chat()` / `chat_stream()` 的接口签名
- 不要改 `prompt_loader.py`
- 不要删任何现有的 prompt YAML 文件
- 不要引入新依赖（`json_repair` 已在 venv 中）
- 不要改 ExerciseAgent / PathAgent 的 StateGraph 拓扑（节点数/边不变）

---

产出文件：.claude-loop/active/04-claude-plan.md | Round DAY04-001
