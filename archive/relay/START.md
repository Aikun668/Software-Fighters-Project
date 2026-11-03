# 一页启动说明

1. 把压缩包中的 `.claude/` 和 `relay/` 复制到你当前项目**根目录**。
2. `python3 relay/relay.py check` 检查文件。
3. 总督终端：`claude --model haiku` → `/g-governor 检查当前项目，把我要做的下一项功能拆成合适任务包`
4. 总督填好 `relay/tasks/T001.md`（必须写验收标准），Worker 终端：`claude --model haiku` → `/g-worker T001`
5. Worker 写 `relay/reports/T001.md`；总督审查后在 `QUEUE` 中更新状态。
6. Worker：`/clear` → `/g-worker T002`；总督需要退休时：`/g-retire` → `/clear` → `/g-governor 继任`。

**警戒线**：80K 收束，90K 交接，别习惯性跨 100K。CLI `/context` 观察，不是自动硬限流。

替代启动：
```bash
python3 relay/relay.py governor "实现 SSE 原生流式事件"
python3 relay/relay.py worker T001
```
