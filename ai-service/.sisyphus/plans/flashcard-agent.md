# FlashCardAgent 开发计划

## 目标
创建 FlashCardAgent，从 ContentAgent 产出的 content_blocks 中自动提取核心概念，生成问答对闪卡。

## 背景
赛题「学习效果评估」加分项需要复习机制，闪卡是最直接的实现。与 ExerciseAgent 形成「学习→记忆→测验」闭环。

## 任务清单

### 1. 新建 `app/agents/flashcard_agent.py`
- FlashCardState TypedDict
- FlashCardAgent 类继承 BaseAgent
- _extract_node: 从 content_blocks 提取关键概念
- _generate_node: LLM 生成问答对（5-8张卡）
- 输出格式：`{"type": "flash_cards", "cards": [{"front", "back"}]}`

### 2. 新建 `prompts/flashcard_agent/system.yaml`
- 角色定义：知识提取与闪卡生成专家
- 任务说明：从教学内容提取核心概念，生成简洁问答对
- 输出格式要求：JSON 数组，每张卡包含 front/back
- 示例：2-3张样例卡

### 3. 修改 `app/workflows/resource_gen.py`
- Director 路由增加 flashcard
- DEFAULT_AGENTS 增加 "flashcard"
- 并行执行：和 mindmap/reading/code 一起跑
- 收集结果到 all_blocks
- 持久化到 DB（type="flash_cards"）

### 4. 修改 `app/utils/ppt_exporter.py`
- 支持 flash_cards block 导出
- 布局：正面问题大字号，背面答案小字号

### 5. 修改 `app/orchestration/director.py`
- TOPIC_AGENT_MAP 增加 flashcard 映射
- 不是所有主题都需要，根据内容类型判断

### 6. 新建 `tests/test_flashcard_agent.py`
- 测试提取逻辑
- 测试生成逻辑（mock LLM）
- 测试输出格式

### 7. 验证
- python -m pytest tests/test_flashcard_agent.py -v
- python -m pytest tests/ -v（确保不回归）

## 约束
- 不修改现有 Agent 的核心逻辑
- 保持现有测试全部通过（当前 ~180 tests）
- prompt 用 YAML 格式，放 prompts/flashcard_agent/
- 不新增外部依赖

## TODOs

### 1. 新建 `prompts/flashcard_agent/system.yaml`
**What to do**:
- system prompt：角色定义 + 设计原则 + 输出格式要求 + 示例
- user_template：接收 topic, content_summary, key_concepts 变量
- 要求 LLM 输出纯 JSON：`{"cards": [{"front": "...", "back": "..."}]}`
- front 为问题/概念，back 为核心答案，每张卡聚焦一个概念
- 数量：5-8张

**Must NOT do**:
- 不输出 markdown code block 包裹的 JSON
- 不在 JSON 外添加解释文字

**Acceptance Criteria**:
- [ ] YAML 文件能被 `build_prompt()` 正确加载
- [ ] 包含 system + user_template 两个 key
- [ ] 输出格式要求明确

---

### 2. 新建 `app/agents/flashcard_agent.py`
**What to do**:
- `FlashCardState` TypedDict：topic, content_blocks, key_concepts, cards, response
- `FlashCardAgent(BaseAgent)`：
  - `build_graph()`: extract → generate，线性两节点
  - `_extract_node()`: 从 content_blocks 提取 heading + 关键句子，拼接为 content_summary 和 key_concepts
  - `_generate_node()`: 调用 LLM，prompt 注入 topic + content_summary + key_concepts
  - `_parse_cards()`: 解析 LLM JSON 输出，验证 cards 数组结构
  - `create_turn_summary()`: override，提取 cards 数量作为 metrics
- 输出：`{"type": "flash_cards", "heading": "核心概念速记", "content": {"cards": [...]}}`

**Must NOT do**:
- 不直接修改 content_blocks（只读取）
- 不生成超过 10 张卡
- 不生成 front/back 为空的卡

**Acceptance Criteria**:
- [ ] `FlashCardAgent` 能独立运行 `agent.run(state)`
- [ ] mock LLM 返回 JSON 时正确解析 cards
- [ ] LLM 返回非 JSON 时降级为空 cards，不抛异常
- [ ] 创建 turn summary，metrics 包含 card_count

---

### 3. 修改 `app/workflows/resource_gen.py`
**What to do**:
- `DEFAULT_AGENTS` 增加 `"flashcard"`（第 38 行）
- `__init__` 中 `self.flashcard_agent = FlashCardAgent(...)`
- `_generate_node()` Step B：
  - flashcard_state 构建（topic, content_blocks）
  - agent_task_map 增加 `"flashcard": (self.flashcard_agent, flashcard_state)`
- Step C：收集 flashcard 结果（和 mindmap/reading/code 同逻辑）
- Step D：all_blocks extend flashcard blocks
- _persist_node：增加 `flash_cards` type 持久化

**Must NOT do**:
- 不改 ContentAgent/ExerciseAgent 的现有逻辑
- 不破坏其他 Agent 的并行执行

**Acceptance Criteria**:
- [ ] flashcard 参与并行执行（和 mindmap/reading/code 一起）
- [ ] flashcard 结果正确聚合到 all_blocks
- [ ] DB 持久化包含 flash_cards type

---

### 4. 修改 `app/orchestration/director.py`
**What to do**:
- `TOPIC_AGENT_MAP` 中所有模式的 agent 列表增加 `"flashcard"`
- `DEFAULT_AGENTS` 增加 `"flashcard"`

**Must NOT do**:
- 不改路由策略（rule/llm）
- 不改 profile_filter 逻辑

---

### 5. 修改 `app/utils/ppt_exporter.py`
**What to do**:
- 新增 `elif block_type == "flash_cards":` 分支
- 布局：标题页 + 每页一张卡（正面大字号问题，背面小字号答案）
- 或列表布局：一页显示所有卡片（正面 + 背面）

**Acceptance Criteria**:
- [ ] PPT 导出包含 flash_cards block
- [ ] 内容正确渲染

---

### 6. 新建 `tests/test_flashcard_agent.py`
**What to do**:
- `TestFlashCardAgentExtract`：
  - test_extract_from_content_blocks：验证从 blocks 提取 summary
  - test_extract_empty_blocks：空输入返回空
- `TestFlashCardAgentGenerate`：
  - test_generate_cards_mock_llm：mock LLM 返回 JSON，验证 cards 结构
  - test_generate_non_json_fallback：mock 返回文本，验证降级为空
  - test_generate_llm_failure：mock 抛异常，验证不崩溃
- `TestFlashCardAgentIntegration`：
  - test_full_run：端到端运行，验证输出包含 type="flash_cards"

**Acceptance Criteria**:
- [ ] 全部测试通过
- [ ] mock 隔离，不依赖真实 LLM

---

### 7. 全量测试验证
**What to do**:
```bash
cd ai-service
python -m pytest tests/test_flashcard_agent.py -v
python -m pytest tests/ -v
```

**Acceptance Criteria**:
- [ ] test_flashcard_agent.py：全部通过
- [ ] 全量测试：不回归（与之前通过数一致）

---

## QA Scenarios

### Happy Path
```python
state = {
    "topic": "梯度下降",
    "content_blocks": [
        {"type": "section", "heading": "梯度下降原理", "content": "梯度下降是一种优化算法..."},
        {"type": "callout", "heading": "学习率", "content": "学习率控制参数更新步长..."},
    ]
}
result = await agent.run(state)
assert result["type"] == "flash_cards"
assert len(result["content"]["cards"]) >= 5
assert all("front" in c and "back" in c for c in result["content"]["cards"])
```

### Error Path
```python
# LLM 返回非 JSON
mock_llm.chat.return_value = "这是普通文本"
result = await agent.run(state)
assert result["type"] == "flash_cards"
assert result["content"]["cards"] == []  # 降级为空
```

### Edge Case
```python
# 空 content_blocks
state = {"topic": "x", "content_blocks": []}
result = await agent.run(state)
assert result["content"]["cards"] == []
```

## Verification Commands
```bash
python -m pytest tests/test_flashcard_agent.py -v
python -m pytest tests/test_workflows.py -v
python -m pytest tests/test_api.py -v
python -m pytest tests/ -q
```

## Estimated Effort
2-3 小时
