# Claude 修复计划 | Round DAY03-002 | 2026-05-27

## 任务 ID
TASK-DAY03-002

## 任务类型
fix（Day 3 Builder 产出修复 — 6 HIGH + 精选 MEDIUM）

## 背景
Day 3 Builder 完成了 4 Agent + 11 Prompt + API 改造。Claude 审查发现 6 HIGH 问题，经与另一 AI 交叉验证，确认 5.5/6 HIGH 属实。本计划修复所有 HIGH 问题 + 值得修的部分 MEDIUM。

---

## 借鉴对齐说明

每个修复标注借鉴来源：

| 修复项 | 借鉴来源 | 借鉴了什么 |
|--------|----------|-----------|
| Fix 2 内容交付 | **OpenMAIC** `scene-outlines-stream` | done 事件携带载荷，客户端一次性拿完整内容 |
| Fix 3 输出校验 | **DeepTutor** `_llm_writer.py:llm_json()` | `_json_has_expected(data, expected_key)` 解析后校验 |
| Fix 5 subsections | **DeepTutor** `page_planner.py:_build_block()` | 按 outline.subsections 逐块生成，params 向下传递 |
| Fix 6 画像注入 | **DeepTutor** `page_planner.py` | proposal 级 profile 通过 params 传入所有子 prompt |
| Fix 4 输入校验 | **OpenMAIC** API routes + **ProfileAgent** 自身 | guard-clause 校验 + 统一 400 返回 |
| Fix 1 中文编码 | **本项目 ProfileAgent line 93**（唯一正确的位置）| 已有 `ensure_ascii=False` 示范 |

---

## Fix 1：SSE 中文编码 — `ensure_ascii=False`

**问题**：7 处 `json.dumps()` 含中文但缺 `ensure_ascii=False`，客户端收到 `\uXXXX` 转义序列。

**文件**：`internal_api.py`

**修改**：每处 `json.dumps({...})` 中若有中文字符，加 `ensure_ascii=False`。

| 行号 | 内容 | 操作 |
|------|------|------|
| 90 | `{'type': 'token', 'content': char}` | 加 `ensure_ascii=False` |
| 111 | `f'正在分析「{topic}」的知识点结构...'` | 加 `ensure_ascii=False` |
| 119 | `'大纲生成完成'` | 加 `ensure_ascii=False` |
| 126 | `f'正在生成「{topic}」{block["type"]}...'` | 加 `ensure_ascii=False` |
| 153 | `{'type': 'token', 'content': char}` | 加 `ensure_ascii=False` |
| 172 | `f'正在规划「{topic}」的练习题...'` | 加 `ensure_ascii=False` |
| 183 | `f'已生成 {num_q} 道题目'` | 加 `ensure_ascii=False` |
| 185 | `{'type': 'done', 'questions': ...}` | 加 `ensure_ascii=False`（题目含中文） |

**参考**：本项目 line 93 已正确使用 `ensure_ascii=False`，直接复制其写法。

**验证**：
```bash
curl -X POST http://localhost:8001/internal/tutor/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":1, "messages":[{"role":"user","content":"你好"}]}'
# 预期：SSE 中看到「你好」而非「你好」
```

---

## Fix 2：`/internal/resources/generate` 交付实际内容

**问题**：endpoint 发 5 条 progress 后发空 `done`，content_blocks 从未发送。

**文件**：`internal_api.py`，`_generate_node` 所在行 87-102

**借鉴 OpenMAIC**：`scene-outlines-stream/route.ts` 的 `done` 事件携带完整 payload：
```typescript
controller.enqueue(encoder.encode(`data: ${JSON.stringify({type: 'done', outlines: parsedOutlines})}\n\n`));
```
客户端从 `done` 事件一次性拿全部数据。

**修改 A** — `internal_api.py` line 121-128：

```python
# 改前：
for block in content_blocks:
    await asyncio.sleep(0.5)
    yield f"data: {json.dumps({'type': 'progress', ...})}\n\n"
yield f"data: {json.dumps({'type': 'done'})}\n\n"

# 改后：每个 block 发 progress + content，done 携带完整 payload
for i, block in enumerate(content_blocks):
    await asyncio.sleep(0.3)
    yield f"data: {json.dumps({'type': 'progress', 'stage': 'generating', 'index': i+1, 'total': len(content_blocks), 'block_type': block['type']}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'type': 'content_block', 'data': block}, ensure_ascii=False)}\n\n"

yield f"data: {json.dumps({'type': 'done', 'content_blocks': content_blocks, 'response': state.get('response', '')}, ensure_ascii=False)}\n\n"
```

新增事件类型 `content_block`，每条带一个 content block 数据。`done` 带完整 `content_blocks` 数组。客户端可以逐块渲染（收到 content_block 就显示一个）或等 done 批量处理。

**修改 B** — `content_agent.py` line 87-102（见 Fix 5，联动修改）

---

## Fix 3：`_plan_node` 解析后校验 outline 结构

**问题**：Mock LLM 返回 `{"updates":{...}}`（profile JSON），`json.loads()` 成功但 outline 拿到了错误结构（缺 `subsections`），`_generate_node` 拿到的是一个只有 `updates`/`knowledge_base` 等键的 dict。

**文件**：`app/agents/content_agent.py`，`_plan_node`

**借鉴 DeepTutor**：`_llm_writer.py:llm_json()` 模式 —— 解析 JSON 后立即校验 `expected_key` 是否存在，不在则 fallback：

```python
# DeepTutor 做法：
data = await _once(None)
if _json_has_expected(data, expected_key):
    return data
# 不满足 → 重试或 fallback
```

我们的项目没有 retry 机制，所以简化为：解析 → 校验结构 → 不满足就用 fallback。

**修改** — `content_agent.py` line 69-83：

```python
# 改前：
try:
    result = await self.plan_llm.chat(...)
    outline = json.loads(result)
except Exception as e:
    logger.error(f"Content plan failed: {e}")
    outline = {...fallback...}

# 改后：
try:
    result = await self.plan_llm.chat(
        [{"role": "user", "content": user_filled}],
        system_prompt=outline_prompt,
    )
    outline = json.loads(result)
    # 借鉴 DeepTutor _json_has_expected 模式：校验关键字段
    if not isinstance(outline.get("subsections"), list) or len(outline.get("subsections", [])) == 0:
        raise ValueError(f"Outline missing subsections, got keys: {list(outline.keys())}")
except (json.JSONDecodeError, ValueError, ConnectionError, RuntimeError) as e:
    logger.error(f"Content plan failed: {e}")
    outline = {
        "intro": f"本节介绍{topic}的核心概念。",
        "subsections": [
            {"heading": f"{topic}基础概念", "role": "core", "focus": topic, "target_words": 300},
            {"heading": f"{topic}核心原理", "role": "core", "focus": f"{topic}原理", "target_words": 350},
            {"heading": f"{topic}实践应用", "role": "application", "focus": f"{topic}应用", "target_words": 300},
        ],
        "key_takeaway": f"掌握{topic}的基本原理和应用方法。",
    }
```

关键变化：
1. 异常类型从 `Exception` 收窄为 `(json.JSONDecodeError, ValueError, ConnectionError, RuntimeError)`（对齐 ProfileAgent）
2. JSON 解析成功后加 `isinstance(outline.get("subsections"), list)` 结构校验
3. fallback outline 从 1 个 subsection 扩展为 3 个（配合 Fix 5 的生成逻辑）

---

## Fix 4：`/internal/tutor/chat` 输入校验

**问题**：`tutor_chat` 没有任何输入校验，而 `profile_chat` 有完整的 messages 类型+非空校验。

**文件**：`internal_api.py`，`tutor_chat` 函数（line 133-157）

**借鉴**：直接复制 `profile_chat`（line 73-76）的校验代码。

**修改** — 在 line 137 `agent = _get_tutor_agent()` 之前插入：

```python
@router.post("/tutor/chat")
async def tutor_chat(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    user_id = body.get("user_id", 1)
    student_profile = body.get("student_profile", {})

    # 借鉴 profile_chat 的校验模式
    if not messages or not isinstance(messages, list):
        return JSONResponse(
            {"error": "messages must be a non-empty list"}, status_code=400
        )

    agent = _get_tutor_agent()
    ...
```

同时对 `resources_generate` 和 `exercise_generate` 加基础校验：

**`resources_generate`** (line 100-108 之后)：
```python
body = await request.json()
student_id = body.get("student_id", "")
topic = body.get("topic", "").strip()
if not topic:
    return JSONResponse({"error": "topic is required"}, status_code=400)
```

**`exercise_generate`** (line 160-168 之后)：
```python
body = await request.json()
topic = body.get("topic", "").strip()
count = body.get("count", 3)
if not topic:
    return JSONResponse({"error": "topic is required"}, status_code=400)
if not isinstance(count, int) or count < 1 or count > 20:
    return JSONResponse({"error": "count must be an integer between 1 and 20"}, status_code=400)
```

---

## Fix 5：`_generate_node` 使用 outline.subsections

**问题**：`_generate_node` 硬编码 5 个 content block，忽略 `outline.subsections`。

**文件**：`app/agents/content_agent.py`，`_generate_node`（line 87-102）

**借鉴 DeepTutor**：`SectionArchitect._build_block()` → 每个 subsection 对应一个 block，block type 由 subsection role 决定。

DeepTutor 的映射：`role=core → SECTION, role=example → CODE, role=application → SECTION, role=comparison → CALLOUT`

**修改**：

```python
async def _generate_node(self, state: ContentState) -> dict:
    """根据 outline.subsections 逐块生成内容"""
    topic = state.get("topic", "")
    outline = state.get("outline", {})
    subsections = outline.get("subsections", [])
    intro = outline.get("intro", f"{topic}介绍")

    content_blocks = []

    # intro block
    content_blocks.append({
        "type": "section",
        "heading": "概述",
        "content": intro,
    })

    # 按 subsections 逐块生成（借鉴 DeepTutor 的 role→type 映射）
    for i, sub in enumerate(subsections):
        heading = sub.get("heading", f"第{i+1}节")
        role = sub.get("role", "core")
        focus = sub.get("focus", topic)

        if role == "example":
            block_type = "code"
            content = f"# {heading}\n# 示例：{focus}\nprint('示例代码 - {topic}')"
        elif role in ("comparison", "application"):
            block_type = "callout"
            content = f"> **{heading}**\n>\n> {focus}\n>\n> 本节对比了{topic}在不同场景下的应用。"
        else:  # core, derivation, 其他
            block_type = "section"
            content = f"## {heading}\n\n{focus}\n\n本节详细讲解{topic}的核心知识点，帮助学生建立扎实的理论基础。"

        content_blocks.append({
            "type": block_type,
            "heading": heading,
            "content": content,
        })

    # 末尾追加思维导图
    mindmap_nodes = [{"id": "root", "label": topic}]
    for i, sub in enumerate(subsections):
        mindmap_nodes.append({"id": f"sub_{i}", "label": sub.get("heading", f"第{i+1}节")})

    content_blocks.append({
        "type": "mindmap",
        "heading": "知识结构",
        "content": json.dumps({
            "nodes": mindmap_nodes,
            "edges": [{"src": "root", "dst": f"sub_{i}"} for i in range(len(subsections))],
        }, ensure_ascii=False),
    })

    # key_takeaway
    key_takeaway = outline.get("key_takeaway", f"掌握{topic}的核心原理。")
    content_blocks.append({
        "type": "callout",
        "heading": "关键要点",
        "content": key_takeaway,
    })

    response = f"已为您生成「{topic}」的学习内容，共 {len(content_blocks)} 个内容块。"
    return {"content_blocks": content_blocks, "response": response, "stage": "generated"}
```

**内容块数量**：`2 (intro + key_takeaway) + len(subsections) + 1 (mindmap) + 1 (takeaway)` → 动态跟随 outline。

**注意**：当 `subsections` 为空时（fallback 仍未触发），回退到 `intro` block + 静态内容。

---

## Fix 6：content_agent 子 prompt 注入 `{student_profile}`

**问题**：5 个 content_agent 子 prompt（outline/code/deep_dive/mindmap）缺失 `{student_profile}` 变量。DeepTutor 的对应文件原本也没有这个变量——但我们的系统有更丰富的画像，应该注入。

**借鉴 DeepTutor**：DeepTutor 在 page_planner 层将 `target_level` 通过 `proposal_block` 字符串传入，而非独立变量。我们的优势是有 6 维画像，应作为独立变量注入。

### 6A：YAML 文件修改

**文件**：`prompts/content_agent/outline.yaml`

在 `user_template` 区块末尾追加：
```yaml
  **学生画像**：
  {student_profile}
  
  请根据学生画像调整大纲的深度和侧重点：
  - 知识基础较低时，增加基础概念类 subsection，减少高阶内容
  - 有明确薄弱点时，增加对应方向的补救内容
  - 有兴趣方向时，在示例和应用中偏向该方向
```

**文件**：`prompts/content_agent/code.yaml`、`deep_dive.yaml`、`mindmap.yaml`

在 `user_template` 末尾追加：
```yaml

  **学生画像**：{student_profile}
```

### 6B：ContentAgent 传参修改

**文件**：`app/agents/content_agent.py`，`_plan_node`

line 58-67，`interpolate_variables` 调用中新增 `student_profile`：

```python
user_filled = interpolate_variables(
    user_prompt,
    {
        "topic": topic,
        "topic_summary": f"关于{topic}的知识讲解",
        "objectives": "理解核心概念，掌握基本原理",
        "focus_topic": topic,
        "knowledge_context": "",
        "student_profile": self._format_profile(student_profile),  # 新增
    },
)
```

新增 helper（参考 TutorAgent._format_profile 的写法）：
```python
def _format_profile(self, profile: dict) -> str:
    """将画像格式化为 prompt 可用的文本"""
    if not profile:
        return "（暂无学生画像，按默认难度生成）"
    lines = []
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
    return "\n".join(lines) if lines else "（暂无学生画像，按默认难度生成）"
```

**注意**：`_format_profile` 与 TutorAgent 的同名方法几乎一样。避免重复，可以提取到 `app/utils/profile_formatter.py` 作为共享工具。但为了减少变更范围，本计划中两个 Agent 各自保留一份（后续可统一重构）。

---

## 附：精选 MEDIUM 修复（顺手修）

以下 MEDIUM 问题改动量极小，一并修掉：

### M1：TutorAgent `except Exception` 收窄
**文件**：`app/agents/tutor_agent.py` line 81
```python
# 改前：except Exception as e:
# 改后：
except (ConnectionError, RuntimeError) as e:
```
对齐 ProfileAgent 的异常处理模式。

### M2：删除 3 个未使用的 import
| 文件 | 删除 |
|------|------|
| `tutor_agent.py:1` | `import json`（未使用） |
| `tutor_agent.py:8` | `from app.services.llm_service import SparkLLM`（未使用，只用 base 的 self.llm） |
| `exercise_agent.py:9` | `from app.utils.prompt_loader import interpolate_variables`（未使用） |
| `path_agent.py:9` | `from app.utils.prompt_loader import interpolate_variables`（未使用） |

### M3：PathAgent 删除 dead `start_level`
**文件**：`app/agents/path_agent.py` line 54, 62, 68
删除三处 `start_level = "基础"/"进阶"/"高级"` 赋值。

### M4：PathAgent 不可变修改
**文件**：`app/agents/path_agent.py` line 109-111
```python
# 改前（就地修改）：
for step in steps:
    if any(i in step["topic"] for i in interest):
        step["status"] = "recommended"

# 改后（创建新对象）：
steps = [
    {**step, "status": "recommended" if any(i in step["topic"] for i in interest) else step.get("status", "pending")}
    for step in steps
]
```

---

## 修改文件清单

| 文件 | 修改类型 | 涉及的 Fix |
|------|---------|-----------|
| `internal_api.py` | 修改 | Fix 1 (7行 ensure_ascii), Fix 2 (content_blocks 交付), Fix 4 (3 端点校验) |
| `app/agents/content_agent.py` | 修改 | Fix 3 (outline 校验), Fix 5 (subsections 生成), Fix 6B (注入 student_profile) |
| `prompts/content_agent/outline.yaml` | 修改 | Fix 6A (新增 student_profile 变量) |
| `prompts/content_agent/code.yaml` | 修改 | Fix 6A (新增 student_profile 变量) |
| `prompts/content_agent/deep_dive.yaml` | 修改 | Fix 6A (新增 student_profile 变量) |
| `prompts/content_agent/mindmap.yaml` | 修改 | Fix 6A (新增 student_profile 变量) |
| `app/agents/tutor_agent.py` | 修改 | M1 (收窄异常), M2 (删 import) |
| `app/agents/exercise_agent.py` | 修改 | M2 (删 import) |
| `app/agents/path_agent.py` | 修改 | M2 (删 import), M3 (删 dead code), M4 (不可变) |

**不改的文件**：
- `exercise_agent/pipeline.yaml` — `{weak_points}` 已有部分画像注入，完整画像由 system.yaml 层传入，结构不变
- `exercise_agent/followup.yaml` — `{question_context}` + `{user_message}` 是其特化变量名，语义正确
- `app/services/llm_service.py` — Mock 机制不变，由各自 Agent 做输出校验

---

## 验证方式

```bash
# 1. 导入验证
cd ai-service && python -c "
from app.agents.tutor_agent import TutorAgent
from app.agents.content_agent import ContentAgent
from app.agents.exercise_agent import ExerciseAgent
from app.agents.path_agent import PathAgent
print('All imports OK')
"

# 2. ContentAgent outline 校验
python -c "
import asyncio
from app.agents.content_agent import ContentAgent
agent = ContentAgent(use_mock_llm=True)
state = asyncio.run(agent.run({'topic': 'CNN', 'student_profile': {}}))
outline = state.get('outline', {})
blocks = state.get('content_blocks', [])
print(f'subsections: {len(outline.get(\"subsections\", []))}')
print(f'content_blocks: {len(blocks)}')
# 预期：subsections >= 1（fallback 3 个或 LLM 返回的），content_blocks 跟随 subsections 数量
"

# 3. SSE 中文编码
curl -s -X POST http://localhost:8001/internal/tutor/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":1, "messages":[{"role":"user","content":"你好"}]}'
# 预期：SSE 中看到中文「你好」而非 \uXXXX

# 4. 内容交付
curl -s -X POST http://localhost:8001/internal/resources/generate \
  -H "Content-Type: application/json" \
  -d '{"student_id":"1", "topic":"机器学习基础"}'
# 预期：SSE 中包含 content_block 事件 + done 事件带 content_blocks 数组

# 5. 输入校验
curl -s -X POST http://localhost:8001/internal/tutor/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":1}'
# 预期：400 {"error": "messages must be a non-empty list"}

curl -s -X POST http://localhost:8001/internal/resources/generate \
  -H "Content-Type: application/json" \
  -d '{}'
# 预期：400 {"error": "topic is required"}

# 6. Spark API 无回归
python test_spark_api.py
# 预期：3/3 passed
```

---

## 执行顺序

```
1. Fix M2+M3+M4（删 dead code，改动最小，先清场）
2. Fix 6A（YAML 加变量，纯文本）
3. Fix 6B + Fix 3 + Fix 5（ContentAgent 大修，联动最多）
4. Fix M1（TutorAgent 异常收窄）
5. Fix 1 + Fix 2 + Fix 4（internal_api.py 三合一）
6. 全量验证
```

---

产出文件：.claude-loop/active/03-claude-fix-plan.md | Round DAY03-002
