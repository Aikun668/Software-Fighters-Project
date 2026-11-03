# GOVERNOR_WILL｜总督遗书（每次重要状态变化都更新）

- 最近更新：2026-10-21（D-016 真机二次事故修复：交互图组件被"done 后 URL 同步→会话重载"清掉——QuestionNavChat suppressAutoReload 修复 + auto_center 图解增强跳过冗余；**浏览器 DOM 级端到端验证通过**（ConvWindow 渲染/存活/可交互），后端已重启加载全部修复）
- 当前分支 / HEAD：for-work（HEAD 为 D-016 提交，见 git log）
- 入库时间线：…→ ec45d1b → 94e6de4（D-014）→ cd68034（D-015）→ D-016 提交（suppressAutoReload + 图解增强跳过）
- 工作区未提交改动：约 23 项同事半成品原样保留；**另含 D-014/D-015 的 system.yaml 提示词改动（能力清单+豁免，与同事 5 行 WIP 同文件无法分离提交，同事入库时务必保留该段）**

## 当前目标
1. D-016 已完成并经浏览器 DOM 级验证：新会话首条消息交互图稳定渲染且 done 后不被清掉、可点击交互、回答约 20 秒（图解增强跳过生效）。
2. **验收方法论教训（D-015/D-016）**：SSE 协议层验证（httpx 直连）≠浏览器渲染层验证——必须用真浏览器走完整链路（5173→8080→8001）做 DOM 级验收。
3. 已知边界：历史会话回放不显示交互图（block 未落库，正文正常）；KB 向量库 512/384 维度不匹配报错（环境问题，检索降级不阻塞）；模型附围栏为高概率非 100%（temperature>0），极端情况会答 Mermaid 静态图。
4. E2E 复跑脚本（temp_file/）：e2e_viz_check.py（直连后端）、e2e_gateway_check.py（真实账号过网关，验证码从 Redis 读）、e2e_isolate_check.py（变量隔离实验）。

## 待用户决定
1. 催同事入库（约 23 项 WIP）——入库后补提交 system.yaml 能力清单段、拍板两套图表通道（ui-block vs done.blocks html）去留
2. 交互图落库持久化（历史会话回放图表）是否立项

## 过程问题（需记录）
- 2026-10-21 D-016：组件"闪没"根因是前端路由联动（done→router.replace→watch→openConversation 重载+清空），单测全绿+协议层全过都发现不了，只有真浏览器能暴露
- 自动化浏览器窗口后台化会被系统节流（ERR_NETWORK_IO_SUSPENDED），E2E 等待期间须保持前台
- E2E 直连 8001/8080 需 httpx trust_env=False（系统代理劫持 localhost 返回 502）
- KB chromadb 512/384 维度不匹配刷屏报错（环境问题、非本线）

## 重大决策 / 风险 / 禁区
- 参见 `DECISIONS.md`（D-001 至 D-016）。核心：D-004/D-007/D-010/D-014（协议与能力扩展）、D-015（三端同步守卫+passthrough）、D-016（suppressAutoReload+图解增强跳过）
- 禁区不变：不覆盖/不 stash 他人未提交改动；提交只 add 本任务文件；不新增依赖；不推送

## 给下一任一句话
先校验 `git status`、QUEUE 与测试现状再继续；改完 Python 重启 8001、前端让用户刷新页面；新增 ui-block 类型同步五处（后端 parser/前端 schema+registry/渲染层映射/fixtures/prompt），三端守卫测试兜底；验收必须真浏览器 DOM 级，别只信协议层；system.yaml 能力清单段未入库，同事入库后记得补提交。
