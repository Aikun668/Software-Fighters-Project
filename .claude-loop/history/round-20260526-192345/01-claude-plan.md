# Claude 计划 | Round DAY01-ALL | 2026-05-26

## Day 1 总览

今天是第十五届中国软件杯大赛的第一天开发任务。核心目标：
1. 完成三层架构的基础设施搭建
2. 确保各层能独立启动
3. 打通前后端通信
4. 验证讯飞星火 API 可调通

---

## 任务 ID
TASK-DAY01-001

## 任务类型
config（配置修改）

## 目标
将项目数据库配置从 PostgreSQL 改为 MySQL（已确认使用 MySQL）

## 背景
项目初始配置使用了 PostgreSQL，但团队决定使用 MySQL。需要修改 Java 后端和 Python AI 微服务的数据库驱动配置。

## 验收标准
- [ ] backend/pom.xml 的数据库驱动已改为 mysql-connector-j
- [ ] ai-service/requirements.txt 的 asyncpg 已改为 aiomysql
- [ ] Python 依赖重新安装成功，可以 import aiomysql
- [ ] 后端同学已被通知需要修改 application.yml 的连接字符串

## 关键文件
| 文件路径 | 操作 | 说明 |
|---------|------|------|
| backend/pom.xml | 修改 | 第 39-41 行，删除 PostgreSQL 依赖，添加 MySQL 依赖 |
| ai-service/requirements.txt | 修改 | 第 13 行，asyncpg>=0.29.0 改为 aiomysql>=0.2.0 |

## 约束条件
- 不修改其他依赖包
- 不修改业务代码
- 不修改 src/ 目录下的任何文件

## 验证方式
```bash
# 验证 Python 依赖
cd ai-service
pip install -r requirements.txt
python -c "import aiomysql; print('aiomysql 导入成功')"

# 验证 Java 依赖（需要 Maven）
cd backend
mvn dependency:tree | grep mysql
```

## 给 DeepSeek 的注意事项
- MySQL 驱动包名是 `mysql-connector-j`（不是旧版的 `mysql-connector-java`）
- aiomysql 版本建议 `>=0.2.0`
- pom.xml 中删除 PostgreSQL 依赖时，注意保留其他依赖不变
- 修改完成后需要通知后端同学修改 application.yml 中的连接字符串：
  ```yaml
  spring:
    datasource:
      url: jdbc:mysql://localhost:3306/ai_edu?useSSL=false&serverTimezone=UTC
      driver-class-name: com.mysql.cj.jdbc.Driver
  ```

---
产出文件：.claude-loop/active/01-claude-plan.md | Round DAY01-001
