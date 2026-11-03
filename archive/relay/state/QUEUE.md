# QUEUE｜单一任务队列（总督维护）

| 优先级 | 任务 | 状态 | 依赖 | 下一步 |
|---|---|---|---|---|
| - | T001 聊天正文 Markdown 与行内公式渲染排查修复 | done（已提交 e904b1b） | 无 | 无 |
| - | T002 AttentionMatrix.vue 组件 | done（已提交 d288976；worktree 与分支已清理） | 无 | 无 |
| - | T003 结构化 UI block 的前端 schema 校验与 registry | done（已提交 2bb9b5e；ui-blocks 41/41） | T002 | 无 |
| 高 | HEAD 修复：katex 依赖与 CSS 补提交 | done（已提交 3fa2754；worktree 验证 markdown 46/46） | 无 | 无 |
| 高 | AttentionMatrix 删除 weights 着色分支（P2/D-007 复审） | done（已提交 69e6bbc；48/48 通过） | T002 | 无 |
| 高 | P5：AttentionMatrix 浏览器/移动端视觉验收（补欠账） | done（2026-10-20 真浏览器 1280/739/390 三尺寸全 PASS；证据在 docs/聊天界面优化/acceptance/） | T002 | 无 |
| 高 | 行渐变与选中白点还原（D-012 对照 GPT 参考复盘） | done（已提交 30e8c99；AttentionMatrix 8/8＋真浏览器色值核验） | T002 | 无 |
| 高 | T005 后端 `visualization` SSE 事件协议（方案 A，D-010） | done（已提交 789a002；pytest 37/37 总督复跑通过） | T003 schema（只读参照） | 无 |
| - | T006 后端把 `visualization` 事件接入 tutor 内容流程（发射机关：抽取 ui-block 围栏→校验→独立事件下发） | done（已提交 e90a02a；总督复跑 89/89） | T005 | 无 |
| - | T004 ChatThread 接入 `visualization` 渲染（接收机关：解析事件→渲染组件→非法降级→围栏残留剥离） | done（已提交 8677564；总督全量 278 复跑＋干净副本 208 通过；ChatThread 手术剥离入库，同事 diff 完好保留在工作区） | T003、T005、T006 | 无 |
| 高 | T007 端到端点亮：QuestionNavChat 接线＋提示词教 LLM 输出 ui-block 围栏 | done（已提交 a17fbab；前端 278/278＋后端 88/88 总督复跑；AITutor/ProfileChat 为静态壳无接线点未动；system.yaml 手术剥离入库，同事 5 行完好保留） | T004、T006 | 无 |
| 高 | 真实环境端到端联调（真 LLM＋Java 网关＋前端，Playwright 实测） | done（2026-10-20 两轮点亮：25 格交互矩阵渲染＋点击说明栏验证，截图存 docs/聊天界面优化/acceptance/；追加 44d33f2 提示词改硬＋ec45d1b 围栏豁免声明；后端已重启至最新） | T007 | 自动触发合规率待与同事提示词 WIP 对齐 |

状态统一：`planned` → `doing` → `review` → `done`；受阻为 `blocked`。
每次总督验收 Worker 后同步更新。**同一个工作树同时只允许一个 doing Worker。**
