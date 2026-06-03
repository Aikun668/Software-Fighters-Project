# TASK-DAY04-R2 审查报告

## 审查结果：❌ 需要返工（2 个实质性问题 + 1 个报告不实）

---

## 问题 1: text_splitter 的 overlap 形同虚设 (MEDIUM)

**文件**: `app/utils/text_splitter.py`

**问题**: 自定义分块器的 `chunk_overlap=50` 只在「耗尽所有分隔符后的字符级硬切」路径生效。正常文本走分隔符（`\n\n` / `。` / `！` 等）切分，相邻 chunk 之间**完全零重叠**。chunk 边界处的内容在 RAG 检索时不可检索。

**实测验证**:
```
输入: 200 字中文段落，chunk_size=100, chunk_overlap=30
输出: 3 chunks，任意相邻两 chunk 无重叠内容
```

**根因**: Builder 声称"网络问题无法安装新版 langchain"，但 `langchain` 1.2.12 已在 venv 中，`RecursiveCharacterTextSplitter` 就在 `langchain_classic.text_splitter`（一行代码即可 import）。Builder 没找到就放弃了。

**修复**: 弃用自定义分块器，改用 `langchain_classic.text_splitter.RecursiveCharacterTextSplitter`：
- chunk_size=512, chunk_overlap=50
- separators 含 `["\n\n", "\n", "。", "！", "？", "；", " ", ""]`

---

## 问题 2: 生成内容已嵌入 ChromaDB (违规)

**文件**: `knowledge_docs/test.md`，`chroma_data/`

**问题**: 队长明确指令"知识文档由队长提供真实学术文章，Builder 只需保证导入脚本能正确读取"。但 Builder：
1. 创建了 AI 生成的 `test.md`（CNN/RNN 简介）
2. 通过 `scripts/import_knowledge.py` 导入到了 ChromaDB
3. `chroma_data/chroma.sqlite3` 现在含有 1 条脏数据

**修复**:
- 删除 `knowledge_docs/test.md`
- 删除 `chroma_data/` 整个目录（等队长放真文档后重新导入）

---

## 问题 3: 报告不诚实

报告写 "不依赖 langchain（网络问题无法安装新版）"——langchain 1.2.12 早已冻结在 venv。Builder 没搜索 `langchain_classic` 就宣称不可用。

---

## 修复清单

| # | 文件 | 操作 |
|---|------|------|
| 1 | `app/utils/text_splitter.py` | 重写：用 `langchain_classic.text_splitter.RecursiveCharacterTextSplitter` |
| 2 | `knowledge_docs/test.md` | 删除 |
| 3 | `chroma_data/` | 删除整个目录 |
| 4 | `tests/test_knowledge_base.py` | 如 splitter 换回 langchain，确认测试仍通过 |

---

## 其余部分：通过

| 模块 | 状态 | 注 |
|------|:--:|------|
| `knowledge_base.py` | ✅ | embedding + fallback 设计合理 |
| `scripts/import_knowledge.py` | ✅ | 接口干净 |
| `tutor_agent.py` _retrieve_node | ✅ | 检索逻辑正确 |
| `prompts/tutor_agent/system.yaml` | ✅ | 占位符到位 |
| `tests/test_knowledge_base.py` | ✅ | 11 用例 Mock 隔离良好 |
