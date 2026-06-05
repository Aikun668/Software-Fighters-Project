# Claude 计划 | Round DAY05-003 | 2026-05-30

## 任务 ID
TASK-DAY05-003

## 任务类型
feature

## 目标
新增 Mermaid 图表生成和 PPT 导出能力，让 AI 产出的概念图谱和思维导图可渲染、资源内容可打包为 .pptx 文件。

## 背景
当前 content_agent 输出纯文本 content_blocks，概念关系只存在 JSON 结构里，学生不可见。比赛隐含加分项：多模态资源输出。对标 DeepTutor 的 Mermaid concept graph 渲染 + OpenMAIC 的 pptxgenjs 导出。

## 验收标准
- [ ] `concept_graph_to_mermaid(graph)` 将 `{nodes: [{id, label}], edges: [{from, to, label}]}` 转换为合法 Mermaid `graph TD` 语法
- [ ] `mindmap_to_mermaid(mindmap)` 将 `{root, children: [{topic, subtopics}]}` 转换为 Mermaid `mindmap` 语法
- [ ] `export_to_pptx(content_blocks, output_path, title)` 将 content_blocks 渲染为 .pptx，支持 section/code/callout/text 四种 block type 的幻灯片布局
- [ ] content_agent 的 `_generate_node` 输出中新增 `"mermaid"` 类型的 content_block（含概念图 Mermaid 代码）
- [ ] `POST /internal/resources/export-pptx` 端点，接收 content_blocks + title → 返回 pptx 文件路径
- [ ] `requirements.txt` 新增 `python-pptx>=0.6.21`
- [ ] `python -m pytest tests/test_mermaid.py tests/test_ppt_export.py -v` 全部通过
- [ ] `python -m pytest tests/ -v` 现有测试不回归

## 关键文件
| 文件路径 | 操作 | 说明 |
|---------|------|------|
| `app/utils/mermaid_generator.py` | 新建 | concept_graph_to_mermaid + mindmap_to_mermaid |
| `app/utils/ppt_exporter.py` | 新建 | export_to_pptx |
| `app/agents/content_agent.py` | 修改 | _generate_node 新增 mermaid block |
| `internal_api.py` | 修改 | 新增 export-pptx 端点 |
| `requirements.txt` | 修改 | 新增 python-pptx |
| `tests/test_mermaid.py` | 新建 | Mermaid 语法生成测试 |
| `tests/test_ppt_export.py` | 新建 | PPT 导出测试（用 tempfile） |

## 约束条件
- 不能修改 `app/agents/` 下 content_agent 以外的文件
- 不能修改 `app/services/` 下任何文件
- Mermaid 生成是纯函数，不依赖网络或外部服务
- PPT 导出必须处理 `python-pptx` 未安装的情况，抛 `ImportError` 并记录日志
- 导出的 .pptx 文件放在 `ai-service/exports/` 目录下，目录不存在时自动创建
- 不要修改现有 content_block 类型的处理逻辑，只新增 mermaid 类型

## 验证方式
```bash
cd ai-service
python -m pytest tests/test_mermaid.py tests/test_ppt_export.py -v
python -m pytest tests/ -v
```

## 给 DeepSeek 的注意事项
- Mermaid 节点标签里的引号要转义（`"` → `'`），否则 Mermaid 渲染器会报语法错误
- `concept_graph_to_mermaid` 的入参可能缺少 `nodes` 或 `edges` key——空 graph 返回最小合法语法（`"graph TD\n"`），不抛异常
- PPT 用 16:9 宽屏比例（13.333 x 7.5 英寸），正文代码块用等宽字体 Consolas
- section type → 标题页布局，code type → 代码页（小字号等宽），callout type → 大字加粗布局
- 测试 PPT 导出时用 `tempfile` 模块生成临时路径，测试完后清理
- `internal_api.py` 的新端点放在 `/resources/export-pptx`，不要在 /exercise/grade 后面插入（避免合并冲突）

---
产出文件：.claude-loop/active/01-claude-plan.md | Round DAY05-003
