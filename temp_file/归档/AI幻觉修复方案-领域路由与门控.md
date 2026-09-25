# AI 幻觉修复方案：领域路由 + 相关性门控

> **问题**：用户说「我数学不好，喜欢看视频学数学」，AI 输出神经网络、梯度下降、计算机视觉——全链路 6 层 AI 偏向叠加放大。
> **目标**：让非 AI 问题用通用知识回答，AI 领域问题才启用知识库/类比库/AI 专用 prompt。

---

## 一、6 层根因 → 修复策略映射

| # | 根因 | 严重度 | 修复策略 | 复杂度 |
|---|------|--------|---------|--------|
| 1 | System prompt 硬编码"人工智能导论课程" | **致命** | 动态 system prompt：按领域切换 | 中 |
| 2 | 知识库 100% AI 内容 | **致命** | 相关性门控：低相关不注入 KB | 低 |
| 3 | Topic 关键词仅含 AI 术语 | 高 | 删除硬编码列表，改用 LLM/用户原文提取 | 低 |
| 4 | 默认 topic="AI基础" | 高 | 默认改为用户原始输入，不做 AI 替换 | 低 |
| 5 | Analogy 类比库全是 AI | 中 | 门控：非 AI 领域不触发类比注入 | 低 |
| 6 | Profile 画像累积 AI 偏好 | 中 | 画像中 course_id 区分领域，非 AI 对话不受 AI 画像干扰 | 中 |

---

## 二、核心方案：三层门控架构

```
用户消息
  │
  ▼
┌─────────────────────────────┐
│  Layer 1: 领域路由器         │  ← 新增
│  DomainRouter.classify()    │
│  → ai / general / math / ...│
└──────────┬──────────────────┘
           │
     ┌─────┴─────┐
     │           │
  [AI 领域]   [非 AI 领域]
     │           │
     ▼           ▼
┌─────────┐ ┌──────────────┐
│ Layer 2 │ │ Layer 2      │
│ 相关性   │ │ 跳过 KB/     │  ← 新增门控
│ 门控    │ │ 类比/专用    │
│         │ │ prompt       │
└────┬────┘ └──────┬───────┘
     │             │
     ▼             ▼
┌─────────┐ ┌──────────────┐
│ Layer 3 │ │ Layer 3      │
│ 动态     │ │ 通用教育     │  ← 动态 prompt
│ AI 专用  │ │ 助手 prompt  │
│ prompt   │ │              │
└────┬────┘ └──────┬───────┘
     │             │
     └──────┬──────┘
            ▼
        LLM 生成
```

### 2.1 Layer 1 — 领域路由器（DomainRouter）

**做什么**：判断用户当前在聊什么领域，决定走 AI 专用管线还是通用管线。

**判断依据**（多信号融合）：

| 信号 | 权重 | 说明 |
|------|------|------|
| KB 向量相似度 top-1 score | 高 | 最高相关文档的 cosine 距离，< 阈值则说明不在 AI 领域 |
| Topic 关键词命中 | 中 | 命中 AI 术语 → 加权；命中通用词 → 不触发 |
| Course ID（来自 Java） | 高 | Java 传入的 `course_id` 直接告诉 Python 当前课程 |
| 意图分类结果 | 低 | `profile_building`/通用问答 → 不强制走 AI |

**实现方式**：纯规则，不需要 LLM，零延迟。

```python
# 伪代码
class DomainRouter:
    AI_THRESHOLD = 0.6          # KB cosine similarity threshold
    AI_COLLECTIONS = {"ai_intro", "ml_basics", "dl_advanced"}

    def classify(self, query: str, course_id: str, kb_results: list[dict]) -> str:
        # 信号 1: Java 传入的 course_id（最权威）
        if course_id and course_id in self.AI_COLLECTIONS:
            return "ai"

        # 信号 2: KB 向量相似度
        if kb_results and kb_results[0].get("score", 0) < self.AI_THRESHOLD:
            return "general"   # 最高分的文档都不像 AI，说明用户不在聊 AI

        # 信号 3: 关键词快速判断
        if self._has_ai_keywords(query):
            return "ai"

        return "general"
```

### 2.2 Layer 2 — 相关性门控（Relevance Gate）

**做什么**：即使判定为 AI 领域，也要检查检索到的 KB 内容是否与当前问题**真的相关**。防止"数学"→"梯度下降"这种弱相关注入。

**门控规则**：

1. **KB 内容注入门控**：top-1 similarity < 0.5 → 不注入 KB 上下文，LLM 用自己的知识回答
2. **Analogy 注入门控**：只在 `concept` 字段精确匹配时才注入（当前是模糊子串匹配，太宽松）
3. **Profile 上下文门控**：依据 `course_id` 只注入对应课程的画像维度，不跨课程污染
4. **默认 topic 门控**：如果 topic 来自 fallback 而非用户显式提及，标注 `confidence: low`，不优先使用

### 2.3 Layer 3 — 动态 System Prompt

**做什么**：根据领域，切换不同的 system prompt。

```
当前（硬编码）:
  你是智能答疑助手，专注于人工智能导论课程。

改为（动态注入）:
  你是智能答疑助手{domain_context}。

  domain_context:
    AI 领域   → "，当前课程为《人工智能导论》。优先使用知识库内容。"
    通用领域  → "。用通用知识回答学生问题，不受特定课程限制。"
```

---

## 三、具体改动清单

### 改动 1：新增 `DomainRouter`（~60 行，新文件）

```
app/services/domain_router.py
```

- `classify(query, course_id, kb_results) → "ai" | "general"`
- `should_inject_kb(threshold) → bool`
- `should_inject_analogy(concept, query) → bool`

### 改动 2：System Prompt 动态化（改 1 个 YAML + tutor_agent.py）

`prompts/tutor_agent/system.yaml`：
```yaml
system: |
  你是智能答疑助手{domain_context}。
  ...（其余不变）
```

`tutor_agent.py._respond_node()`：
```python
domain = router.classify(query, course_id, kb_results)
domain_context = (
    "，当前课程为《人工智能导论》。优先使用知识库内容回答。"
    if domain == "ai" else
    "。用通用知识回答学生问题，涵盖各类学科。"
)
system_with_context = interpolate_variables(
    self.system_prompt,
    {"domain_context": domain_context, ...}
)
```

### 改动 3：KB 注入门控（改 tutor_agent.py 的 _retrieve_node / _respond_node）

```python
# _respond_node 中
knowledge_context = state.get("knowledge_context", "")
if knowledge_context:
    # 门控检查：知识库内容与用户问题是否真的相关
    kb_score = state.get("kb_top_score", 0)
    if kb_score < 0.5:
        knowledge_context = ""  # 不注入不相关内容
```

### 改动 4：Analogy 门控（改 tutor_agent.py + analogy_library.py）

```python
# 当前：子串模糊匹配
if query_lower in entry.concept.lower() or query_lower in entry.analogy.lower():

# 改为：精确匹配 + 领域门控
def search(self, concept: str, domain: str = "ai") -> list[AnalogyEntry]:
    if domain != "ai":
        return []  # 非 AI 领域直接跳过
    # ... 原有精确匹配逻辑
```

### 改动 5：移除硬编码 AI 默认值（改 intent_extractor.py）

```python
# 当前
class ExerciseParams(BaseModel):
    topic: str = Field(default="AI基础", ...)

# 改为
class ExerciseParams(BaseModel):
    topic: str = Field(default="", ...)  # 空默认，由调用方传入
```

`_extract_topic()` 的 fallback：
```python
# 当前：提取不到就返回 "AI基础"
return " ".join(candidates[:3])[:30] or "AI基础"

# 改为：提取不到就返回用户原始消息的前 30 字符
return " ".join(candidates[:3])[:30] or message[:30]
```

### 改动 6：Topic 关键词从硬编码 → 从知识库元数据动态读取

```python
# 当前：硬编码 19 个 AI 术语
TOPIC_KEYWORDS = ["机器学习", "深度学习", ...]

# 改为：从 KB 的 module metadata 动态加载
def _load_topic_keywords_from_kb() -> list[str]:
    kb = get_kb()
    modules = kb.get_all_modules()  # 从 embedding_metadata 读取
    return modules  # ["人工智能概论", "机器学习", "深度学习", ...]
```

---

## 四、方案对比：三选一

| 方案 | 范围 | 工作量 | 效果 | 风险 |
|------|------|--------|------|------|
| **A. 最小改动** | 仅加门控（改动 3+4+5） | 0.5 天 | 阻止 80% 幻觉 | 非 AI 问题 LLM 用自己的知识回答（无 KB 增强） |
| **B. 门控 + 路由器** | 改动 1-6 全部 | 1.5 天 | 阻止 95% 幻觉，支持多领域扩展 | 需要 Java 传 course_id |
| **C. 多课程架构** | B + KB 多集合 + 课程路由 | 3 天 | 完全通用，任意课程 | 知识库需要为每个课程准备内容 |

### 推荐：先做方案 B（门控 + 路由器）

理由：
- 改动量适中，核心逻辑集中在 2 个新文件 + 3 个文件修改
- 基本不改现有数据/知识库结构
- 通过 `course_id` 参数即可支持未来多课程
- 非 AI 问题不注入 KB/类比/AI prompt，LLM 用自身知识回答——这本身就是合理行为

---

## 五、实现优先级

| 优先级 | 改动 | 影响 |
|--------|------|------|
| P0 | 改动 3：KB 注入门控 | 单点最大改善——不相关内容不再注入 |
| P0 | 改动 5：移除 AI 默认值 | 消除"所有问题 topic 都变成 AI" |
| P1 | 改动 1+2：DomainRouter + 动态 prompt | 系统性解决 AI 定位问题 |
| P1 | 改动 4：Analogy 门控 | 防止类比库喧宾夺主 |
| P2 | 改动 6：Topic 关键词动态化 | 为多课程扩展做准备 |

---

## 六、门控阈值建议

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| KB cosine 相似度阈值 | 0.5 | 低于此值不注入 KB，需根据实际 embedding 模型调优 |
| Analogy 匹配方式 | 精确子串 OR 向量相似度 > 0.7 | 从当前模糊匹配收紧 |
| KB top-K | 从 3 降到 2 | 减少噪声注入 |
| 领域判定信号优先级 | course_id > KB similarity > keywords | Java 权威 > 向量距离 > 规则兜底 |
