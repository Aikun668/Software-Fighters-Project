# Claude 计划 | Round DAY01-004 | 2026-05-26

## 任务 ID
TASK-DAY01-004

## 任务类型
infra（数据层基础设施）

## 目标
创建 4 个 SQLAlchemy 数据库模型（User、StudentProfile、Resource、LearningRecord）。这是 Python 和 Java 共享的数据库表结构定义，后续所有功能都依赖这 4 张表。

## 背景
Python（你用 SQLAlchemy）和 Java（后端同学用 MyBatisPlus）操作同一个 MySQL 数据库。你定义的字段名、字段类型、JSON 结构决定了 Java 端怎么写。**你是数据格式的定义者**。

## 验收标准
- [ ] `ai-service/app/models/user.py` 已创建，User 模型包含 id/username/email/password_hash/created_at
- [ ] `ai-service/app/models/profile.py` 已创建，StudentProfile 包含完整的 6 维画像字段
- [ ] `ai-service/app/models/resource.py` 已创建，Resource 包含 type/topic/content_json/file_path
- [ ] `ai-service/app/models/learning_record.py` 已创建，LearningRecord 包含 progress/score/time_spent
- [ ] `ai-service/app/models/__init__.py` 导出所有模型
- [ ] `ai-service/app/db/database.py` 已创建，配置 MySQL 数据库连接
- [ ] 所有模型可以正常 import，无报错

## 关键文件
| 文件路径 | 操作 | 说明 |
|---------|------|------|
| ai-service/app/models/user.py | 新建 | 用户表模型 |
| ai-service/app/models/profile.py | 新建 | 学生画像表模型（6维） |
| ai-service/app/models/resource.py | 新建 | 学习资源表模型（5种类型） |
| ai-service/app/models/learning_record.py | 新建 | 学习记录表模型 |
| ai-service/app/models/__init__.py | 修改 | 添加模型导出 |
| ai-service/app/db/database.py | 新建 | 数据库连接配置 |

## 约束条件
- 不修改 main.py、llm_service.py、base_agent.py
- 所有模型继承 SQLAlchemy 的 `Base`（declarative_base）
- 所有表名用复数、snake_case
- JSON 字段用 SQLAlchemy 的 `JSON` 类型（MySQL 8.0 原生支持）
- 时间字段用 `DateTime`，默认 `func.now()`
- 数据库连接字符串从 .env 读取：`mysql+aiomysql://root:password@localhost:3306/ai_edu`
- **Python 端只定义模型，不执行建表**（建表由 Java 端的 MyBatisPlus 自动完成）

## 验证方式
```bash
cd ai-service
python -c "
from app.models import User, StudentProfile, Resource, LearningRecord
print('User:', User.__tablename__)
print('StudentProfile:', StudentProfile.__tablename__)
print('Resource:', Resource.__tablename__)
print('LearningRecord:', LearningRecord.__tablename__)
print('所有模型导入成功')
"
```

## 给 DeepSeek 的注意事项

### 模型 1：User（用户表）

表名：`users`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer, PK, autoincrement | 自增主键 |
| username | String(50), unique, not null | 用户名 |
| email | String(100), unique, not null | 邮箱 |
| password_hash | String(255), not null | 密码哈希（bcrypt） |
| created_at | DateTime, default=func.now() | 注册时间 |

### 模型 2：StudentProfile（学生画像表）— 赛题核心

表名：`student_profiles`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer, PK, autoincrement | 自增主键 |
| user_id | Integer, FK→users.id, unique | 关联用户，一对一 |
| knowledge_base | Integer, default=0 | **维度1**：知识基础（0-100） |
| cognitive_style | String(50) | **维度2**：认知风格（visual/auditory/kinesthetic/theoretical） |
| learning_goal | String(500) | **维度3**：学习目标 |
| weak_points | JSON | **维度4**：易错点列表，如 `["梯度下降", "反向传播"]` |
| learning_pace | String(50) | **维度5**：学习节奏（fast/steady/slow） |
| interest_direction | JSON | **维度6**：兴趣方向，如 `["CV", "NLP", "RL"]` |
| raw_profile_json | JSON | 完整画像快照，保存 LLM 原始输出 |
| updated_at | DateTime, default=func.now() | 最后更新时间 |

### 模型 3：Resource（学习资源表）

表名：`resources`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer, PK, autoincrement | 自增主键 |
| user_id | Integer, FK→users.id | 所属用户 |
| type | String(50), not null | 资源类型：course_doc/mind_map/exercise/reading/code_practice |
| topic | String(200), not null | 知识点名称，如 "卷积神经网络" |
| title | String(300) | 资源标题 |
| content_json | JSON | 资源内容（Markdown/JSON/题目数据） |
| file_path | String(500) | 文件路径（如果有的话） |
| created_at | DateTime, default=func.now() | 生成时间 |

### 模型 4：LearningRecord（学习记录表）

表名：`learning_records`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer, PK, autoincrement | 自增主键 |
| user_id | Integer, FK→users.id | 所属用户 |
| resource_id | Integer, FK→resources.id | 关联资源 |
| progress | Float, default=0.0 | 完成进度（0-100） |
| score | Float | 得分（0-100） |
| time_spent | Integer | 学习时长（秒） |
| created_at | DateTime, default=func.now() | 记录时间 |

### 数据库连接（database.py）

```python
# 伪代码示意，不是完整实现
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base

DATABASE_URL = os.getenv("DATABASE_URL")  # 从 .env 读取
# 当前 .env 中是：mysql+aiomysql://root:password@localhost:3306/ai_edu

engine = create_async_engine(DATABASE_URL, echo=False)
Base = declarative_base()  # 所有模型继承这个
```

### 给后端同学的字段对照表（写在报告里，方便他复制）

```
表1: users
  id INT PK, username VARCHAR(50) UNIQUE, email VARCHAR(100) UNIQUE,
  password_hash VARCHAR(255), created_at DATETIME

表2: student_profiles
  id INT PK, user_id INT FK UNIQUE, knowledge_base INT DEFAULT 0,
  cognitive_style VARCHAR(50), learning_goal VARCHAR(500),
  weak_points JSON, learning_pace VARCHAR(50),
  interest_direction JSON, raw_profile_json JSON,
  updated_at DATETIME

表3: resources
  id INT PK, user_id INT FK, type VARCHAR(50),
  topic VARCHAR(200), title VARCHAR(300),
  content_json JSON, file_path VARCHAR(500),
  created_at DATETIME

表4: learning_records
  id INT PK, user_id INT FK, resource_id INT FK,
  progress FLOAT DEFAULT 0.0, score FLOAT,
  time_spent INT, created_at DATETIME
```

---
产出文件：.claude-loop/active/01-claude-plan.md | Round DAY01-004
