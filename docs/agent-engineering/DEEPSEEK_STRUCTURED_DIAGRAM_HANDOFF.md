# DeepSeek Harness：结构化交互图解任务交接

先阅读：

1. `AGENTS.md`
2. `docs/superpowers/specs/2026-08-16-structured-interactive-diagram-design.md`
3. `docs/agent-engineering/DEEPSEEK_IMPLEMENTATION_HANDOFF.md`

## 你的任务

把 `interactive_diagram` 从模型生成 HTML 改为模型生成 Schema v1，补一个 Vue SVG 受控渲染组件。不要接入静态演示的资源工坊/对话页，不要重构资源工作流，不要把 diagram 切为 `active`。

## 执行顺序

1. 先写后端 schema 校验与 Agent fallback 的失败测试。
2. 修改 Prompt 和 `InteractiveDiagramAgent`，移除 HTML/脚本输出路径。
3. 扩展 `ResourceValidator` 和 diagram Judge 输入。
4. 写 Vue `StructuredDiagram` 组件及组件测试/fixture；不得使用 `v-html`、iframe、外部 CDN 或模型生成脚本。
5. 跑 mock，再跑 3 个真实 Shadow 案例；记录模型产物与 fallback 的来源。

## 硬性边界

- Schema 与验收标准以设计规格为准；不自行扩展为 D3、拖拽或编辑器。
- `content` 质量门控和 safety filter 不在本任务修改范围。
- 图解模型输出解析失败时必须给确定性结构化 fallback，不能返回 HTML。
- 每完成一个逻辑单元，先运行对应测试，再做小粒度提交。

## 完成后反馈

```text
完成状态：完成 / 阻塞
改动文件：...
关键契约：...
验证命令与结果：...
真实 Shadow 证据：模型产物数 / fallback 数 / 人工复核状态
提交：<hash> <message>
需要 Codex 决策：无 / ...
```
