# FlashCardAgent 实现报告

## 完成内容

### 1. 新建 prompts/flashcard_agent/system.yaml
- 定义闪卡生成器的角色和任务
- 要求输出严格 JSON 格式：`{"cards": [{"front": "...", "back": "..."}]}`
- 规则：5-8 张卡，每张聚焦一个核心概念

### 2. 新建 app/agents/flashcard_agent.py
- FlashCardState TypedDict：topic, content_blocks, key_concepts, cards, response
- FlashCardAgent 继承 BaseAgent
- 两节点图：extract → generate
- _extract_node：从 content_blocks 提取 heading 和关键内容
- _generate_node：调用 LLM 生成问答对，支持 fallback
- create_turn_summary：提取 cards 数量作为 metrics

### 3. 修改 app/workflows/resource_gen.py
- DEFAULT_AGENTS 增加 "flashcard"
- __init__ 中初始化 flashcard_agent
- _generate_node 中添加 flashcard_state 和 agent_task_map
- Step C 收集 flashcard turn summary
- Step D 聚合 flashcard blocks
- _persist_node 添加 flash_cards 类型持久化

### 4. 修改 app/orchestration/director.py
- TOPIC_AGENT_MAP 所有模式增加 flashcard
- DEFAULT_AGENTS 增加 flashcard
- LLM prompt 添加 flashcard 说明

### 5. 修改 app/utils/ppt_exporter.py
- 新增 flash_cards 分支处理
- 渲染为结构化文本：Q1/A1, Q2/A2...

### 6. 新建 tests/test_flashcard_agent.py
- 7 个测试全部通过
- 覆盖：提取、生成、非 JSON 回退、LLM 失败、集成、turn summary

### 7. 全量测试验证
- 334 个测试全部通过
- 0 失败，0 回归

## 新增文件
- prompts/flashcard_agent/system.yaml
- app/agents/flashcard_agent.py
- tests/test_flashcard_agent.py

## 修改文件
- app/workflows/resource_gen.py
- app/orchestration/director.py
- app/utils/ppt_exporter.py
- app/services/llm_service.py（添加 PROFILE_FLASHCARD）
- tests/test_orchestration.py（更新 DEFAULT_AGENTS 断言）

## 测试统计
- test_flashcard_agent.py：7/7 通过
- 全量测试：334/334 通过

## 技术细节
- 使用 LangGraph 两节点工作流（extract → generate）
- 支持 LLM 生成 + fallback 双路径
- 卡片数量限制：最多 10 张
- 输出格式：{"type": "flash_cards", "heading": "核心概念速记", "content": {"cards": [...]}}
- 与现有 ExerciseAgent 形成"学习→记忆→测验"闭环

---

# 深度修复报告

## 修复内容

### 1. Prompts 深度重写

**analysis.yaml**：
- 加入 4 种 render_type 的详细定义和适用场景
- 明确选择优先级原则（静态优先，html 最后）
- 扩展输出字段：chart_type、data_description、visual_elements、rationale

**code_generator.yaml**：
- 按 render_type 的具体格式约束：
  - Mermaid：node ID 只能字母数字下划线，中文在方括号内
  - SVG：必须 xmlns + viewBox，font-size >= 14px
  - Chart.js：必须包含 type/data/options，responsive: true
  - HTML：无外部依赖，唯一 ID
- 通用设计原则：5-10 个节点，中文标签 <= 10 字，主色 <= 3 种

**review.yaml**：
- 按 render_type 的专项检查清单（mermaid/svg/chartjs/html 各 4 项）
- `changed` 字段替代 `passed`：true = 已修正，使用 optimized_code

### 2. Bug 修复

| Bug | 文件 | 修复 |
|-----|------|------|
| Review 逻辑反了 | visualize_pipeline.py | `if changed: use optimized_code` |
| Agent 命名冲突 | analysis/code_generator/review_agent.py | 分别命名为 visualize_*_agent |
| Mermaid 偏移计算 | mermaid_parser.py | 使用 match.end() 替代手动计算 |
| Media Adapter 静默失败 | media/__init__.py | 未配置/失败时抛出 RuntimeError |
| api_key="" 被环境变量覆盖 | media/__init__.py | `api_key if api_key is not None else env` |

### 3. Pipeline 字段适配

- `codegen_state` 加入 `chart_type`、`data_description`、`visual_elements`
- `review_state` 加入 `chart_type`、`data_description`
- `CodeGenState` 和 `ReviewState` TypedDict 同步更新

### 4. Pydantic 模型

`app/agents/visualize/models.py`：
- `VisualizationAnalysis`
- `CodeResult`
- `ReviewResult`
- `VisualizeOutput`

## 测试状态
- **465/465 passing**（0 failures）
- 更新测试：test_visualize_pipeline.py、test_media_adapter.py

## 参考率
- 借鉴 DeepTutor prompts 结构和检查清单思路
- 具体规则为原创（基于 Mermaid/Chart.js/SVG 官方文档）