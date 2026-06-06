# Claude 计划 | Round DAY05-001 | 2026-05-30

## 任务 ID
TASK-DAY05-001

## 任务类型
feature

## 目标
新建 `app/utils/content_guard.py`，实现 LLM 输出内容的**事实性校验**和**安全过滤**，并接入 tutor_agent 和 content_agent。

## 背景
当前 LLM 生成的内容直接输出给学生，没有任何审核：
- 可能输出错误知识点（幻觉），学生无从辨别
- 可能被越狱 prompt 诱导输出不安全内容

借鉴 DeepTutor 的 `validate_fact_refs()` 模式：提取知识断言 → 查知识库 → 置信度打分。
借鉴 OpenMAIC 的内容安全检测模式：正则匹配禁止模式。

## 验收标准
- [ ] `ContentSafetyFilter.check(text)` 返回 `(safe: bool, violations: list)`，能检测代码注入、越狱 prompt、Markdown 链接混淆三类危险模式
- [ ] `FactChecker.check_claims(text, kb)` 返回 `[{claim, confidence, evidence}]`，confidence 分 HIGH/MEDIUM/LOW 三档，基于 KB 检索的 cosine distance 判定
- [ ] `FactChecker.extract_claims(text)` 能从文本中拆出知识断言，跳过问句和短碎片
- [ ] tutor_agent 的 `_respond_node` 在流式输出完成后调用 FactChecker，对 LOW 置信度的 claim 追加 `[需要验证]` 标记
- [ ] content_agent 的 `_generate_node` 在每个 content_block 生成后调用 ContentSafetyFilter，拦截 unsafe block
- [ ] `python -m pytest tests/test_content_guard.py -v` 全部通过
- [ ] `python -m pytest tests/ -v` 现有 108 个测试不回归

## 关键文件
| 文件路径 | 操作 | 说明 |
|---------|------|------|
| `app/utils/content_guard.py` | 新建 | ContentSafetyFilter + FactChecker 两个类 |
| `app/agents/tutor_agent.py` | 修改 | _respond_node 结尾处调用 FactChecker |
| `app/agents/content_agent.py` | 修改 | _generate_node 对 content_block 调用 ContentSafetyFilter |
| `tests/test_content_guard.py` | 新建 | 单元测试，mock KB 验证三类置信度和安全检测 |

## 约束条件
- 不能修改 `app/services/knowledge_base.py` 的 search() 接口签名
- 不能修改 `app/utils/embeddings.py`
- 不能修改 `internal_api.py` 的任何端点
- 不能修改 `app/agents/` 下 tutor_agent 和 content_agent 以外的文件
- 必须保持现有 108 个测试通过

## 验证方式
```bash
cd ai-service
python -m pytest tests/test_content_guard.py -v
python -m pytest tests/ -v
```

## 给 DeepSeek 的注意事项
- KB 的 `search()` 返回 `list[{content, metadata, score}]`，其中 score 是 cosine distance（0=完全相同，2=完全相反）。distance<0.5 可视为 HIGH 置信度，0.5-0.8 为 MEDIUM，>0.8 或无结果为 LOW
- ContentSafetyFilter 的正则不要写太宽——只匹配明显的危险模式，避免误杀正常教学内容（比如教"SQL注入"时不应该把教学内容当危险代码拦截）
- `_respond_node` 是 async generator（流式），FactChecker 的调用时机应该在流式输出结束后、yield 最终 done 事件之前
- `_generate_node` 产生的 content_block 结构是 `{type, title, content}`，只对 type 为 "text"/"section"/"callout" 的 block 做安全检测，"code" 类型跳过
- extract_claims 时，问句（以？?结尾）和 <10 字符的碎片不视为知识断言
- 测试里 mock kb.search() 的返回值来模拟各种 distance 场景，不需要真正启动 ChromaDB

---
产出文件：.claude-loop/active/01-claude-plan.md | Round DAY05-001
