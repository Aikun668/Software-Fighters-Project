# TASK-DAY04-R2：ChromaDB RAG 知识库检索接入

## 背景

Day 4 Round 1 完成 5 Agent 真实 LLM 全线打通。Round 2 目标：**TutorAgent 的 `_retrieve_node` 从硬编码 mock → ChromaDB 真实语义检索**。

当前问题：
- `knowledge_base.py` 有 ChromaDB PersistentClient + search + format_context，但 collection 创建时**没绑定 embedding function**——向量检索不工作
- `tutor_agent.py` `_retrieve_node` 还是硬编码 mock 文本
- `prompts/tutor_agent/system.yaml` 没有 `{knowledge_context}` 占位符，即使检索了也注入不进 prompt

---

## 借鉴策略

DeepTutor 用 LlamaIndex，我们不搬框架（ChromaDB 更轻量已够用）。**搬理念不搬代码**：

| 搬什么 | 从哪里看 |
|------|------|
| 分块参数 512/50 + 文档加载流程 | `DeepTutor-参考版/deeptutor/services/rag/pipelines/llamaindex/ingestion.py` |
| 检索结果格式化为 prompt 上下文 | `DeepTutor-参考版/deeptutor/services/rag/pipelines/llamaindex/storage.py`（我们已有 `format_context()`） |
| 文档导入错误处理（缺文件/编码问题不炸） | `DeepTutor-参考版/deeptutor/services/rag/pipelines/llamaindex/document_loader.py` |

**不搬的**：LlamaIndex 框架、FileTypeRouter（只需 .md/.txt）、embedding 多 provider 适配器（ChromaDB 内置 ONNX 够了）、BM25 重排序、索引版本控制。

---

## Step 1: knowledge_base.py — 接入 embedding + 降级容错

**文件**：`app/services/knowledge_base.py`

### 要做的事

1. **绑定 embedding function**：`__init__` 中给 `get_or_create_collection` 传入 `embedding_function=chromadb.utils.embedding_functions.ONNXMiniLM_L6_V2()`。onnxruntime 已在 venv，首次运行自动下载 ~80MB 模型。

2. **新增 `add_documents(texts, metadatas, ids)` 方法**：封装 `collection.upsert()`，自动做 embedding。调用方只需传已分块的文本列表。

3. **`search()` 加关键词降级**：当向量检索返回 0 条或集合为空时，自动降级为简单字符级关键词匹配（中文用字符集匹配即可，不需要分词器）。返回格式与向量检索一致。

4. **新增 `is_empty()`**：返回 `collection.count() == 0`。

### 设计要点
- 关键词降级只需匹配查询中的字符是否出现在文档中，按命中数排序——简单但有效
- embedding function 创建失败时不能崩，降级为空 collection（不影响服务启动）
- `format_context()` 已有，不需要改

---

## Step 2: 文本分块工具

**新建**：`app/utils/text_splitter.py`

用 `langchain.text_splitter.RecursiveCharacterTextSplitter`（已在 requirements.txt）。

- chunk_size=512, chunk_overlap=50（参考 DeepTutor）
- separators 适配中文：`["\n\n", "\n", "。", "！", "？", "；", " ", ""]`
- 提供一个 `split_text(text, source) -> list[dict]`，返回 `[{"content": str, "metadata": {"source": filename, "chunk_index": i}}, ...]`

---

## Step 3: 文档导入脚本

**新建**：`scripts/import_knowledge.py`

### 要做的事
- 扫描指定目录（默认 `knowledge_docs/`，可配置）下所有 `.md` 和 `.txt` 文件
- 每个文件：读入 → `split_text()` 分块 → `kb.add_documents()` 批量入库
- 用 `{filename}_{chunk_index}` 做 id，重复导入自动去重（upsert）
- 打印每个文件的 chunk 数和总统计

### 错误处理
- 文件不存在/编码问题 → 打印警告，跳过该文件，继续处理后续文件
- 空文件 → 跳过

### 注意
知识文档由队长后续放入 `knowledge_docs/`，Builder 只需保证导入脚本能正确工作。可以写一个小的测试用 `.md` 文件自己验证流程。

---

## Step 4: TutorAgent 切真实检索

**文件**：`app/agents/tutor_agent.py`

### `_retrieve_node` 改造
1. 去掉硬编码 mock 文本
2. 调用 `get_kb().format_context(query, top_k=3)` 获取知识上下文
   - query 取 `messages[-1].content`
3. 调用 `kb.is_empty()` 检查，空库 → knowledge_context = ""
4. `get_kb()` 或检索过程异常 → catch 后 knowledge_context = ""，不阻塞对话

### `_respond_node` 无需改动
它已经通过 `interpolate_variables` 注入 `knowledge_context`，只是之前传到 prompt 里被忽略了。

**文件**：`prompts/tutor_agent/system.yaml`

### 改造
- system prompt 中加入 `{knowledge_context}` 占位符，放在「学生画像」之后
- 增加指导语："优先使用知识库内容回答问题；如果知识库没有相关内容，用自己的知识回答。"

---

## Step 5: 测试

**新建**：`tests/test_knowledge_base.py`

至少覆盖：
- 初始化后 embedding_fn 已绑定
- `add_documents` 后 `search` 能检索到
- 空库 `search` 不报错
- `format_context` 格式正确
- `is_empty` 状态正确

**修改**：`tests/test_agents.py`

- `TestTutorAgent.test_knowledge_context`：不再验证硬编码 mock 内容，改为验证 knowledge_context 是 str 即可（可以为空）

---

## 修改文件清单

| 文件 | 操作 |
|------|------|
| `app/services/knowledge_base.py` | 修改 |
| `app/utils/text_splitter.py` | **新建** |
| `scripts/import_knowledge.py` | **新建** |
| `app/agents/tutor_agent.py` | 修改 |
| `prompts/tutor_agent/system.yaml` | 修改 |
| `tests/test_knowledge_base.py` | **新建** |
| `tests/test_agents.py` | 修改（1 个用例） |

---

## 验证

```bash
# 0. 自己写一个 test.md 验证导入流程
echo "# 测试\n卷积神经网络是一种前馈神经网络..." > knowledge_docs/test.md

# 1. 导入
cd ai-service && python scripts/import_knowledge.py

# 2. 验证检索
python -c "
from app.services.knowledge_base import get_kb
kb = get_kb()
print('size:', kb.collection.count())
for r in kb.search('CNN', top_k=2):
    print(r['content'][:80])
"

# 3. 启动服务后测试 RAG 答疑
curl -X POST http://localhost:8001/internal/tutor/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":1, "messages":[{"role":"user","content":"CNN是什么？"}]}'

# 4. 全量测试
python -m pytest tests/ -v
```

---

## 注意事项
1. **ONNX 模型首次下载**约 80MB 到 `~/.cache/chroma/onnx_models/`，确保网络可用。
2. **prompt_loader 的 `interpolate_variables`** 已支持 `{knowledge_context}` 直接插值，不需要改 prompt_loader。
3. **ChromaDB upsert 天然去重**，不需要抄 DeepTutor 的 SHA-256 方案。
4. **不要生成知识文档**——队长会找真实学术文章放入 `knowledge_docs/`。
