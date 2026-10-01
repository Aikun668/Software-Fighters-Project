# acceptance/ —— 验收存证归档

这个目录收纳了 `ai-service` 在做「域收口 / 公共设施抽取」等重构时，用于**字节级回归存证**的脚本与输出快照。它们**不进 pytest**，是手动 `python` 跑的独立 harness，核心目的是证明重构「零行为变化」。

## 目录结构

```
acceptance/
├── harness/            # 8 个存证脚本（可复用，已去 _accept_ 前缀）
├── snapshots/          # 脚本输出快照（before/after/diff 基线，已 .gitignore）
└── dev_acceptance_app.py  # 本地验收用 ASGI 入口（uvicorn 启动）
```

## harness/ 脚本对照表

| 新文件名 | 原文件名 | 用途 / 打的接口 |
|---------|---------|----------------|
| `sse_all_endpoints.py` | `_accept_sse_all_endpoints.py` | 全 8 个 SSE 端点 + 3 个下载守卫 + SSRF，抽取前后逐字节比对 |
| `sse_harness.py` | `_accept_sse_harness.py` | Task 4 SSE 验收，断言 `done.data` 8 字段完整 |
| `tutor_sse.py` | `_accept_tutor_sse.py` | 答疑域收口 `/internal/tutor/chat` |
| `exercise_sse.py` | `_accept_exercise_sse.py` | 练习域收口 `/exercise/generate`、`/solve` |
| `graph_endpoints.py` | `_accept_graph_endpoints.py` | 图谱域 14 个端点字节存证 |
| `plan_endpoints.py` | `_accept_plan_endpoints.py` | 计划域 9 个端点字节存证 |
| `inquiry_resolve.py` | `_accept_inquiry_resolve.py` | 真实 SSE（urllib 连真服务）`/internal/inquiry/resolve` |
| `global_500.py` | `_accept_global_500.py` | 全局 500 信封兜底，before/after 对照 |

## 运行方式

**必须从 `ai-service/` 根目录**用 `-m` 方式运行，否则 `import internal_api` / `import main` 无法解析：

```bash
cd ai-service
python -m acceptance.harness.sse_all_endpoints
python -m acceptance.harness.graph_endpoints before
python -m acceptance.harness.plan_endpoints after
```

几个注意点：

- `graph_endpoints.py` / `plan_endpoints.py` 需要 `before` 或 `after` 参数（在收窄前/后两个 commit 各跑一次，对比 sha256）。
- `inquiry_resolve.py` 走 `urllib` 连**真实运行中的服务**，需先 `uvicorn` 起服务再跑。
- 其余脚本用 `httpx.ASGITransport` 同进程打接口，无需起服务。

## snapshots/ 快照分组

| 子目录 | 内容 |
|--------|------|
| `sse/` | SSE 全端点 before/after/task3/task6/diff、case1 raw |
| `tutor/` | 答疑域收口前后 + metrics 对比 |
| `exercise/` | 练习域原始 SSE |
| `graph/` `plan/` | 图谱/计划域收口前后 |
| `error/` | 错误帧、excinfo、全局 500 信封 |
| `assembly/` | 装配抽取前后 |
| `learning/` | 学习快照域基线 |
| `chat/` `profile/` | 聊天进度帧、画像流水线 |
| `multimodal/` `pkg/` | 多模态、package 契约 |
| `misc/` | final 基线、task3 hashes、`server_output.log`、`rg-sse.txt`、服务启动日志 |

> 根目录的走散 `_accept_*.txt` / `server_*.log` 一律归入对应分类；同名重复副本（`*_after2`、`*_a2`）与逐字节重复项直接丢弃。

`snapshots/` 已在 `ai-service/.gitignore` 中忽略（只保留 `harness/` 脚本进版本库）。若这些快照此前已被 git 跟踪，需执行 `git rm -r --cached acceptance/snapshots/` 才会真正从仓库移除。
