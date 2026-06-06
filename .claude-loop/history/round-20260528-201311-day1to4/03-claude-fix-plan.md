# 03-claude-fix-plan — Builder 代码修复报告 | 2026-05-27

## 修复摘要

审查 02-deepseek-code.md 后发现 2 HIGH + 1 MEDIUM 问题，已直接修复。

---

## Fix 1: `chat_stream()` 补超时 + 异常覆盖 [HIGH]

**文件**: `app/services/llm_service.py`（行 181-211）

**问题**: `chat()` 有 `asyncio.timeout(120) + open_timeout=30 + OSError + TimeoutError`，但 `chat_stream()` 全都没有。ProfileAgent / TutorAgent 走流式调用，OSError / 超时会炸穿 Agent 层的异常捕获。

**修法**: `chat_stream()` 对齐 `chat()`，加 `asyncio.timeout(120.0)`、`open_timeout=30.0`、`OSError` 和 `asyncio.TimeoutError` 捕获，统一转 `RuntimeError`。

---

## Fix 2: ContentAgent `_generate_node` LLM 调用无效 [HIGH]

**文件**: `app/agents/content_agent.py`（行 116-244）

**问题**: 旧代码两个 bug：
1. 没有按 role 路由子 prompt —— 全部用 outline.yaml 调 LLM，expected_key 设 `"subsections"`，但 outline 是大纲 prompt 不是内容生成 prompt
2. LLM 返回后取 `result["subsections"][0].get("focus")` 然后套硬编码模板 `f"## {heading}\n\n{focus}\n\n本节详细讲解..."` —— LLM 产出的内容被丢弃

**修法**: 
- 新增 `_route_block_prompt()` —— 按 role 路由到正确子 prompt：
  - `example` → `code.yaml`（返回 `{"language","code","explanation"}`）
  - `comparison/application` → `deep_dive.yaml`（返回 `{"suggestions": [...]}`）
  - `core/derivation` → `outline.yaml`（返回 `{"intro","subsections","key_takeaway"}`）
- 新增 `_render_block_content()` —— 按 role 从 LLM JSON 输出中提取展示内容：
  - code 类型 → 格式化为 `` ```python ... ``` `` 代码块
  - callout 类型 → 格式化为 `**粗体** + - 要点列表`
  - section 类型 → 格式化为 `intro + ### 子标题`
- 每个 block LLM 失败时 fallback 回硬编码内容（保持向后兼容）

---

## Fix 3: PathAgent `_revise_node` 接入 LLM [MEDIUM]

**文件**: `app/agents/path_agent.py`（行 122-158）

**问题**: `_revise_node` 仍是纯逻辑的 interest 子串匹配，计划要求的 LLM self-critique 没做。

**修法**: `_revise_node` 新增 LLM 自查调用 —— 构建 revise 专用 prompt（"请审查以下学习路径，检查覆盖度、顺序合理性、与画像的匹配度"），调 `_call_llm_json()` 获取 `revised_steps`。LLM 失败时 fallback 回原有的 interest 匹配逻辑。

---

## 变更文件

| 文件 | 变更 |
|------|------|
| `app/services/llm_service.py` | chat_stream() 加超时 + 异常覆盖 |
| `app/agents/content_agent.py` | generate_node 重构：role 路由 + LLM 内容消费 |
| `app/agents/path_agent.py` | revise_node 新增 LLM 自查 |

## 未改

- json_parser.py → 正确
- base_agent.py `_call_llm_json()` → 正确
- profile_agent.py → 正确
- exercise_agent.py → 正确
- .env → 正确
