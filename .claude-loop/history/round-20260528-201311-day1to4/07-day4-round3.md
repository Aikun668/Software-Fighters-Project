# TASK-DAY04-R3：MySQL 画像持久化 + API 画像接入

## 背景

Day 4 Round 1 打通真实 LLM，Round 2 接入 ChromaDB RAG。Round 3 是 Day 4 最后一轮——**把画像真正落到 MySQL，让所有端点能从数据库读画像**。

当前 DB 基础设施已就绪（async engine + 4 个 ORM model + `get_db()` session factory），缺的是：表没建、API 没读画像、没有可复用的 CRUD service。

---

## 借鉴分析

两个参考项目都**不用 MySQL/SQLAlchemy**——DeepTutor 用 raw sqlite3，OpenMAIC 是浏览器 IndexedDB。**本轮没什么代码可搬**，本质是连线工作。

唯一可搬的理念：
- DeepTutor `sqlite_store.py` 的 inline migration（CREATE TABLE IF NOT EXISTS）→ 等同于我们的 `Base.metadata.create_all()`
- DeepTutor `SessionStoreProtocol` 的 service class 封装模式 → 不搬代码，但 service 层封装思想一致

---

## Step 1: 启动建表 + DB 健康检查

**文件**：`main.py`

### 要做的事

1. 加 `@app.on_event("startup")` 事件，调用 `Base.metadata.create_all(bind=engine)` ——确保 4 张表（users, student_profiles, resources, learning_records）在 MySQL 中存在
2. `/health` 端点加 MySQL 连通性检查——执行 `SELECT 1`，成功返回 `{"status": "ok", "db": "connected"}`，失败返回 `{"status": "degraded", "db": "unreachable"}`
3. 建表失败不阻塞启动（打 warning 日志）

### 注意
- `engine` 是懒加载的（`_get_engine()`），需要确保在 startup 事件中正确获取
- `Base.metadata.create_all` 是同步方法，FastAPI startup 事件支持同步

---

## Step 2: Profile CRUD Service

**新建**：`app/services/profile_service.py`

### 要做的事

提供一个 `ProfileService` 类（或函数），封装画像的读写：

1. **`get_profile(user_id) -> dict | None`**
   - 从 `student_profiles` 表查询 `user_id` 对应记录
   - 返回 6 维度 dict：`{"knowledge_base": int, "cognitive_style": str, "learning_goal": str, "weak_points": [...], "learning_pace": str, "interest_direction": [...]}`
   - 记录不存在返回 None
   - DB 异常 → 打印 warning，返回 None

2. **`save_profile(user_id, profile_dict) -> None`**
   - Upsert：存在则更新，不存在则创建
   - DB 异常 → 打印 warning，不抛异常

3. 使用现有的 `get_db()` 获取 async session（`async with get_db() as session`）

### 设计要点
- 不要重复发明 ProfileAgent `_merge_node` 的合并逻辑——那个保留在 Agent 里不变
- Service 层只做「读写」，不做「合并」
- 单例模式（模块级 `_service` 变量 + `get_profile_service()` 工厂函数），与 `get_kb()` 风格一致

### 参照
可参考 `knowledge_base.py` 底部的单例模式：`_kb_instance` + `get_kb()`。

---

## Step 3: API 端点接入画像读取

**文件**：`internal_api.py`

### 要做的事

当前所有 5 个端点都硬编码 `student_profile: {}`（或 `current_profile: {}`），ProfileAgent 存了画像但其他 Agent 读不到。改造每个端点在调用 `agent.run()` 前从 DB 加载：

| 端点 | 当前 | 改为 |
|------|------|------|
| `/profile/chat` | `current_profile: {}` | 调用 profile_service 加载已有画像 |
| `/tutor/chat` | `student_profile: {}` | 调用 profile_service 加载 |
| `/resources/generate` | `student_profile: {}` | 调用 profile_service 加载 |
| `/exercise/generate` | `student_profile: {}` | 调用 profile_service 加载 |
| `/path/{student_id}` | `student_profile: {}` | 调用 profile_service 加载 |

- DB 不可用或画像不存在 → 降级为空 dict（Agent 已能处理空画像）
- 不要在 `event_stream()` 内部做 DB 查询（会阻塞流），在调用 `agent.run()` 之前查好

---

## Step 4: 测试

**新建**：`tests/test_profile_service.py`

覆盖：
- `get_profile` 查到记录返回正确 dict
- `get_profile` 查不到记录返回 None
- `get_profile` DB 异常不抛错，返回 None
- `save_profile` 调用后能 `get_profile` 读到

使用 `unittest.mock` mock 掉 `get_db()` 和 SQLAlchemy session。

---

## 修改文件清单

| 文件 | 操作 |
|------|------|
| `main.py` | 修改（startup 建表 + health DB 检查） |
| `app/services/profile_service.py` | **新建** |
| `internal_api.py` | 修改（5 端点从 DB 加载画像） |
| `tests/test_profile_service.py` | **新建** |

---

## 验证

```bash
# 0. 确保 MySQL 运行中
mysql -u root -p123666 -e "SHOW DATABASES;" 2>/dev/null

# 1. 启动服务，检查建表日志
cd ai-service && python main.py
# 预期日志：无报错

# 2. health
curl http://localhost:8001/health
# → {"status": "ok", "db": "connected"}

# 3. ProfileAgent 对话后查 DB
curl -X POST http://localhost:8001/internal/profile/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":1, "messages":[{"role":"user","content":"我数学基础不好"}]}'
# 查 MySQL 确认写入：
# mysql -u root -p123666 ai_edu -e "SELECT * FROM student_profiles WHERE user_id=1;"

# 4. 其他端点验证从 DB 读到画像（不是空 dict）
curl -X POST http://localhost:8001/internal/tutor/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":1, "messages":[{"role":"user","content":"推荐我学什么？"}]}'
# SSE 输出中应体现画像信息

# 5. 测试
python -m pytest tests/ -v
```
