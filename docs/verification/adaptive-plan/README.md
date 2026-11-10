# 独立验收：动态计划

## 验证层级与限制

- `api-real-check.cjs` 驱动生产 `AdaptivePlanController` / `AdaptivePlanService`，使用真实 H2 SQL 存储和 MockMvc，不是前端假数据。
- `ui-real-check.cjs` 驱动生产构建页面，通过 Playwright 请求路由与同一个后端 stdin bridge 联调。每次运行使用全新隔离内存库，不创建真实用户账号。
- 身份由测试过滤器注入；未验证生产登录、MySQL、网关、真实 LLM 响应。其他非计划 API 返回空数据，避免干扰或读写用户数据。
- API 创建后重新读取、页面刷新验证同一存储实例的持久化；不把 H2 内存测试说成已验证生产重启恢复。
- 截图文件名含 `real-api` 表示真实计划控制器/服务参与，不表示生产环境验收。

## 运行

先在 backend 执行 Maven `test-compile` 并生成测试依赖 classpath，然后：

```sh
ROOT=$(pwd)
(cd backend && mvn test-compile dependency:build-classpath -Dmdep.outputFile=target/test-classpath.txt -DincludeScope=test)
export ADAPTIVE_PLAN_BRIDGE_COMMAND="java -cp $ROOT/backend/target/test-classes:$ROOT/backend/target/classes:$(cat backend/target/test-classpath.txt) com.university.learning.plan.AdaptivePlanBrowserBridge"
node docs/verification/adaptive-plan/api-real-check.cjs
# frontend npm run build 后；受限环境可使用官方 Chromium headless_shell
export PLAYWRIGHT_CHROMIUM_EXECUTABLE=/path/to/headless_shell
node docs/verification/adaptive-plan/ui-real-check.cjs
```

注意 bridge 命令的工作目录是 backend，classpath 应使用绝对路径。脚本为每条后端请求设置 15 秒超时，浏览器等待 10 秒超时。

## API 固定断言

创建字段重读一致；暂停断点重读；预览与取消不改变计划；确认拆分保持总工作量和已完成项；下一步不超过三条；重复确认/过期版本/跨用户/匿名请求拒绝；撤销恢复；新进度后不允许旧撤销覆盖；期限冲突必须明确选择；空远期模块追加任务；延期任务重新列入不丢工作量。

## 浏览器固定断言

真实表单创建；两个真实计划切换后刷新仍保持正确计划；暂停后刷新断点仍在；预览取消无变化；确认拆分并刷新；续学写入；带计划进入聊天不会自动发送或改计划；聊天内预览确认同一计划；撤销恢复；390px 无横向溢出；无页面 JavaScript 异常；远期模块细化后刷新保持；显式刷新续学草稿追加当前版本上下文、保留待发送文字、不自动发送。
