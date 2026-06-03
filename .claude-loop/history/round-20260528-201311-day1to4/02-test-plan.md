# 测试计划 | TASK-TEST-001 | 2026-05-27

## 1. 执行摘要

- **状态**: ✅ 全部通过
- **测试用例**: 75 个
- **通过**: 75/75 (100%)
- **失败**: 0
- **执行时间**: ~2 秒

## 2. 测试文件清单

| 文件 | 用例数 | 类型 | 状态 |
|------|--------|------|------|
| `tests/test_json_parser.py` | 14 | 单元测试 | ✅ 全部通过 |
| `tests/test_prompt_loader.py` | 16 | 单元测试 | ✅ 全部通过 |
| `tests/test_llm_service.py` | 10 | 单元/集成测试 | ✅ 全部通过 |
| `tests/test_agents.py` | 18 | 集成测试 | ✅ 全部通过 |
| `tests/test_api.py` | 17 | 端到端测试 | ✅ 全部通过 |
| **总计** | **75** | - | **✅ 100%** |

## 3. 测试覆盖详情

### 3.1 JSON 解析器 (`test_json_parser.py`)

| 用例 | 描述 |
|------|------|
| test_normal_json | 正常 JSON 解析 |
| test_markdown_code_block | Markdown ```json 包裹提取 |
| test_markdown_without_json_label | Markdown ``` 无标签提取 |
| test_nested_markdown | 嵌在其他文本中的 Markdown |
| test_empty_string | 空字符串返回 fallback |
| test_whitespace_only | 空白字符返回 fallback |
| test_non_json_text | 非 JSON 文本返回 fallback |
| test_custom_fallback | 自定义 fallback 值 |
| test_expected_key_present | expected_key 存在时返回 |
| test_expected_key_missing | expected_key 缺失时 fallback |
| test_broken_json_with_repair | 残缺 JSON 通过 json_repair 修复 |
| test_unicode_content | Unicode 中文内容解析 |
| test_list_response | 列表类型 JSON 解析 |
| test_scalar_fallback | None 作为 fallback |

### 3.2 Prompt 加载器 (`test_prompt_loader.py`)

| 用例 | 描述 |
|------|------|
| test_simple_replacement | 单变量替换 |
| test_multiple_variables | 多变量替换 |
| test_missing_variable_preserved | 缺失变量保留原样 |
| test_dict_value | dict 值自动 JSON 序列化 |
| test_list_value | list 值自动 JSON 序列化 |
| test_none_value | None 值保留占位符 |
| test_empty_variables | 空 variables 不报错 |
| test_none_variables | None variables 不报错 |
| test_condition_true | {{#if true}} 保留内容 |
| test_condition_false | {{#if false}} 删除内容 |
| test_no_conditions | 无条件块直接返回 |
| test_snippet_not_found | 缺失 snippet 返回提示文本 |
| test_no_snippets | 无 snippet 占位符直接返回 |
| test_load_existing_prompt | 加载存在的 prompt 文件 |
| test_load_nonexistent_file | 缺失文件返回空字符串 |
| test_load_nonexistent_key | 缺失 key 返回空字符串 |

### 3.3 LLM 服务 (`test_llm_service.py`)

| 用例 | 描述 |
|------|------|
| test_mock_mode_no_credentials_needed | Mock 模式无需凭据 |
| test_real_mode_requires_credentials | 真实模式需要环境变量 |
| test_mock_chat_response | Mock 非流式调用返回字符串 |
| test_mock_chat_stream | Mock 流式调用返回 chunks |
| test_mock_chat_with_system_prompt | Mock 调用支持 system_prompt |
| test_chat_websocket_success | WebSocket 成功接收消息 |
| test_chat_websocket_error_code | WebSocket 返回错误码抛出 RuntimeError |
| test_chat_timeout | 超时抛出 RuntimeError |
| test_chat_os_error | OSError 抛出 RuntimeError |
| test_build_ws_url | URL 签名包含必要参数 |

### 3.4 Agent 集成 (`test_agents.py`)

| Agent | 用例 | 描述 |
|-------|------|------|
| ProfileAgent | test_initialization | 初始化正确 |
| ProfileAgent | test_run_extracts_profile | 从消息提取画像 |
| ProfileAgent | test_run_with_existing_profile | 合并已有画像 |
| ContentAgent | test_initialization | 初始化正确 |
| ContentAgent | test_run_generates_content | 生成内容块 |
| ContentAgent | test_content_block_structure | 内容块结构正确 |
| ExerciseAgent | test_initialization | 初始化正确 |
| ExerciseAgent | test_run_generates_questions | 生成指定数量题目 |
| ExerciseAgent | test_question_structure | 题目字段完整 |
| ExerciseAgent | test_run_with_weak_points | 薄弱点注入 |
| PathAgent | test_initialization | 初始化正确 |
| PathAgent | test_run_generates_path | 生成学习路径 |
| PathAgent | test_step_structure | 步骤字段完整 |
| PathAgent | test_different_knowledge_levels | 不同知识水平生成不同路径 |
| PathAgent | test_concept_graph_structure | 概念图结构正确 |
| TutorAgent | test_initialization | 初始化正确 |
| TutorAgent | test_run_responds | 生成回复 |
| TutorAgent | test_knowledge_context | 知识上下文非空 |

### 3.5 API 端到端 (`test_api.py`)

#### 输入校验 (9 个用例)
| 用例 | 端点 | 校验规则 |
|------|------|----------|
| test_profile_empty_messages | /profile/chat | messages 不能为空 |
| test_profile_invalid_messages_type | /profile/chat | messages 必须是列表 |
| test_resources_empty_topic | /resources/generate | topic 不能为空 |
| test_tutor_empty_messages | /tutor/chat | messages 不能为空 |
| test_exercise_empty_topic | /exercise/generate | topic 不能为空 |
| test_exercise_count_too_high | /exercise/generate | count <= 20 |
| test_exercise_count_zero | /exercise/generate | count >= 1 |
| test_exercise_count_negative | /exercise/generate | count >= 1 |
| test_exercise_count_string | /exercise/generate | count 必须是整数 |

#### 流式端点 (4 个用例)
| 用例 | 端点 | 验证 |
|------|------|------|
| test_profile_stream | /profile/chat | SSE 格式、200 状态码 |
| test_resources_stream | /resources/generate | SSE 格式、200 状态码 |
| test_tutor_stream | /tutor/chat | 200 状态码 |
| test_exercise_stream | /exercise/generate | 200 状态码 |

#### 路径端点 (2 个用例)
| 用例 | 验证 |
|------|------|
| test_path_response | steps + concept_graph 结构 |
| test_path_step_structure | order/topic/status 字段 |

#### 错误处理 (2 个用例)
| 用例 | 验证 |
|------|------|
| test_404 | 不存在端点返回 404 |
| test_invalid_method | GET /profile/chat 返回 405 |

## 4. Mock 策略

### 4.1 全局 Mock
- `asyncio.sleep`: 全局 autouse fixture 中 mock，加速所有测试

### 4.2 Agent Mock
- `internal_api._get_*_agent`: 在 API 测试中 patch，返回 AsyncMock
- `use_mock_llm=True`: Agent 测试中始终使用 Mock LLM

### 4.3 WebSocket Mock
- `websockets.connect`: 在 LLM 服务测试中 patch
- 自定义 MockAsyncIterator 类模拟 WebSocket 消息流

## 5. 执行命令

```bash
# 运行全部测试
cd ai-service && python -m pytest tests/ -v

# 运行特定模块
python -m pytest tests/test_json_parser.py -v
python -m pytest tests/test_agents.py -v
python -m pytest tests/test_api.py -v

# 覆盖率
pip install pytest-cov
python -m pytest tests/ --cov=app --cov-report=term-missing
```

## 6. 新增文件

```
tests/
├── __init__.py
├── conftest.py                 # 全局 fixtures + asyncio.sleep mock
├── test_json_parser.py         # 14 个用例
├── test_prompt_loader.py       # 16 个用例
├── test_llm_service.py         # 10 个用例
├── test_agents.py              # 18 个用例
└── test_api.py                 # 17 个用例
```

## 7. 关键实现细节

### 7.1 WebSocket Mock
```python
class MockAsyncIterator:
    def __init__(self, items):
        self.items = items
        self.index = 0
    def __aiter__(self):
        return self
    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item
```

### 7.2 异步测试 fixture
```python
@pytest_asyncio.fixture
async def async_client():
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client
```

### 7.3 全局 sleep mock
```python
@pytest.fixture(autouse=True)
def mock_sleep():
    with patch("asyncio.sleep"):
        yield
```

## 8. 结论

- 全部 75 个测试用例通过，覆盖核心功能
- Mock 策略完善，测试运行快速（~2 秒）
- 异步测试使用 pytest-asyncio + ASGITransport
- API 测试同时覆盖同步校验和异步流式端点
- 所有外部依赖（LLM、DB、WebSocket）均已 mock

**产出文件**：`.claude-loop/active/02-test-plan.md` | TASK-TEST-001 ✅
