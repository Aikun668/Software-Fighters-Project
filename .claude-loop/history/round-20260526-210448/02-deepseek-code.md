# DeepSeek 报告 | Round DAY01-005 | 2026-05-26

## 任务 ID
TASK-DAY01-005

## 执行结果
✅ 成功

## 修改文件清单
| 文件 | 操作 | 说明 |
|------|------|------|
| ai-service/internal_api.py | 修改 | `app = FastAPI()` → `router = APIRouter(prefix="/internal")`，4 个端点 mock 数据全面丰富 |
| ai-service/main.py | 修改 | 加 `from internal_api import router` + `app.include_router(internal_router)` |

## 验收标准完成情况
- [x] 4 个端点返回的 mock 数据够逼真（≥5 个 token 的流式输出） → 完成
- [x] internal_api.py 的路由被挂载到 main.py 的 app 上 → 完成（APIRouter + include_router）
- [x] SSE 格式统一：`data: {"type":"token"/"progress"/"done", "content":"..."}\n\n` → 完成
- [x] 启动 main.py 后 4 个端点都可以访问 → 完成
- [x] curl 测试每个端点都能返回正确的 SSE 流 → 完成

## 测试结果
```
=== 1. POST /internal/profile/chat ===
  14 events (12 tokens + profile_update + done)
  SSE types: token, profile_update, done

=== 2. POST /internal/resources/generate ===
  8 events (outline ×2 + generating ×5 + done)
  SSE types: progress, done

=== 3. POST /internal/tutor/chat ===
  28 events (26 tokens with Markdown + code + done)
  SSE types: token, done

=== 4. GET /internal/path/student-001 ===
  5 steps: completed×2, in_progress×1, pending×2

=== /health ===
  {"status": "ok"}
```

## 架构变化
| 改造前 | 改造后 |
|--------|--------|
| `internal_api.py` 独立 `app = FastAPI()` | `router = APIRouter(prefix="/internal")` |
| main.py 和 internal_api.py 各绑 8001 | main.py 通过 `include_router` 统一管理 |
| 每个端点 1 token mock | profile: 12 tokens, tutor: 28 tokens, resources: 7 progress events |

## SSE 事件类型
| type | 用途 | 示例端点 |
|------|------|----------|
| `token` | 流式文本片段 | profile/chat, tutor/chat |
| `progress` | 进度更新，含 stage 字段 | resources/generate |
| `profile_update` | 画像更新，content 为 JSON 字符串 | profile/chat |
| `done` | 流结束 | 全部 SSE 端点 |

---

## 附：User 模型补充（回应后端同学质疑）

`ai-service/app/models/user.py` 在 DAY01-004 基础上新增 3 个 MVP 字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `student_id` | String(20), unique, not null | 学号 |
| `full_name` | String(50), not null | 姓名 |
| `role` | String(20), default="student" | 角色（student/teacher/admin） |

用户表最终字段：`id, student_id, full_name, role, username, email, password_hash, created_at`

---

产出文件：.claude-loop/active/02-deepseek-code.md | Round DAY01-005

