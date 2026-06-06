# Claude 计划 | Round DAY01-003 | 2026-05-26

## 任务 ID
TASK-DAY01-003

## 任务类型
feature + verify（功能验证）

## 目标
补充测试脚本，验证星火 API + BaseAgent 真的能调通。核心代码已经有了，只需要写测试脚本并跑通。

## 背景
好消息：`llm_service.py` 和 `base_agent.py` 已经写好了，代码质量很好。借鉴了 DeepTutor 的设计（Prompt YAML 分离、统一 LLM 接口），同时保持了极简（不引入多提供者、token tracking 等不需要的功能）。现在只需要写测试脚本验证一切能跑通。

## 现有代码审查结论
- ✅ `llm_service.py`（98行）：SparkLLM 类，httpx + 星火 REST API，支持流式/非流式
- ✅ `base_agent.py`（72行）：BaseAgent 抽象基类，LangGraph StateGraph，YAML Prompt 加载
- ✅ 5 个 prompt YAML 文件已存在（均为占位内容）
- ❌ 缺少 `test_spark_api.py` 测试脚本

## 验收标准
- [ ] `ai-service/test_spark_api.py` 已创建
- [ ] 测试脚本能成功调用讯飞星火 API（非流式）
- [ ] 测试脚本能成功调用讯飞星火 API（流式）
- [ ] BaseAgent 和 SparkLLM 可以正常 import
- [ ] 用户已将真实的 API Key 填入 .env（不是占位符）

## 关键文件
| 文件路径 | 操作 | 说明 |
|---------|------|------|
| ai-service/test_spark_api.py | 新建 | 星火 API 测试脚本 |
| ai-service/.env | 确认 | 确保 SPARK_API_KEY 不是占位符 |

## 约束条件
- 不修改 llm_service.py 和 base_agent.py（代码已就绪）
- 不修改 main.py 和 requirements.txt
- 测试脚本要打印清晰的 pass/fail 结果

## 验证方式
```bash
cd ai-service
python test_spark_api.py
# 预期：非流式测试 ✅, 流式测试 ✅
```

## 给 DeepSeek 的注意事项

### 测试脚本要点
- 用 `os.getenv("SPARK_API_KEY")` 读取 Key，用 `dotenv` 加载 .env
- 测试 1：非流式调用 → 发一条消息，打印返回内容长度
- 测试 2：流式调用 → 逐 token 打印，统计总 token 数
- 测试 3：BaseAgent import → from app.agents.base_agent import BaseAgent
- 使用 asyncio.run() 运行异步测试
- 如果 API Key 是占位符，脚本应该明确提示用户先配置

---
产出文件：.claude-loop/active/01-claude-plan.md | Round DAY01-003
