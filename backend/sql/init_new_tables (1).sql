CREATE DATABASE IF NOT EXISTS learning_platform DEFAULT CHARACTER SET utf8mb4;
USE learning_platform;

CREATE TABLE users (
                       id BIGINT PRIMARY KEY AUTO_INCREMENT,
                       username VARCHAR(50) NOT NULL UNIQUE COMMENT '用户名',
                       password VARCHAR(255) NOT NULL COMMENT '密码',
                       real_name VARCHAR(50) COMMENT '真实姓名',
                       email VARCHAR(100) COMMENT '邮箱',
                       phone VARCHAR(20) COMMENT '手机号',
                       avatar_url VARCHAR(500) COMMENT '头像URL',
                       role VARCHAR(20) DEFAULT 'student' COMMENT '角色',
                       status TINYINT DEFAULT 1 COMMENT '0禁用1正常',
                       created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                       updated_at DATETIME ON UPDATE CURRENT_TIMESTAMP,
                       INDEX idx_username (username)
) COMMENT '系统用户表';


CREATE TABLE IF NOT EXISTS student_profiles (
                                                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '画像ID',
                                                user_id BIGINT NOT NULL UNIQUE COMMENT '用户ID',
                                                knowledge_base INT DEFAULT 0 COMMENT '知识基础 0-100',
                                                cognitive_style VARCHAR(50) COMMENT '认知风格: visual/auditory/kinesthetic/theoretical',
                                                learning_goal TEXT COMMENT '学习目标',
                                                weak_points JSON COMMENT '易错点列表',
                                                learning_pace VARCHAR(20) COMMENT '学习节奏: fast/steady/slow',
                                                interest_direction JSON COMMENT '兴趣方向',
                                                raw_profile_json JSON COMMENT '完整画像快照',
                                                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                                INDEX idx_user_id (user_id),
                                                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学生画像表';


CREATE TABLE IF NOT EXISTS resources (
                                         id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '资源ID',
                                         user_id BIGINT NOT NULL COMMENT '用户ID',
                                         type VARCHAR(50) NOT NULL COMMENT '资源类型: course_doc/mind_map/exercise/reading/code_practice',
                                         topic VARCHAR(200) COMMENT '知识点名称',
                                         content_json JSON COMMENT '资源内容',
                                         file_path VARCHAR(500) COMMENT '文件路径',
                                         created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                         INDEX idx_user_id (user_id),
                                         INDEX idx_type (type),
                                         FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学习资源表';


CREATE TABLE IF NOT EXISTS learning_records (
                                                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '记录ID',
                                                user_id BIGINT NOT NULL COMMENT '用户ID',
                                                resource_id BIGINT NOT NULL COMMENT '资源ID',
                                                progress FLOAT DEFAULT 0.0 COMMENT '完成进度 0-100',
                                                score FLOAT COMMENT '得分',
                                                time_spent INT COMMENT '学习时长(秒)',
                                                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                                INDEX idx_user_id (user_id),
                                                INDEX idx_resource_id (resource_id),
                                                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                                                FOREIGN KEY (resource_id) REFERENCES resources(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学习记录表';

CREATE TABLE IF NOT EXISTS file_info (
                                         id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '文件ID',
                                         user_id BIGINT NOT NULL COMMENT '用户ID',
                                         file_name VARCHAR(255) NOT NULL COMMENT '原始文件名',
                                         file_path VARCHAR(500) NOT NULL COMMENT 'MinIO存储路径',
                                         file_size BIGINT COMMENT '文件大小(字节)',
                                         file_type VARCHAR(255) COMMENT '文件类型',
                                         created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                         INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文件信息表';

-- 1. 对话会话
CREATE TABLE IF NOT EXISTS conversations (
                                             id         BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
                                             user_id    BIGINT       NOT NULL              COMMENT '用户ID',
                                             title      VARCHAR(255) NOT NULL DEFAULT '新对话' COMMENT '对话标题',
                                             status     VARCHAR(20)  NOT NULL DEFAULT 'active' COMMENT '状态：active / archived',
                                             summary    TEXT                               COMMENT 'AI生成的对话摘要',
                                             created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                             updated_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                             INDEX idx_user_id (user_id),
                                             INDEX idx_user_status (user_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='对话会话';

-- 2. 会话消息
CREATE TABLE IF NOT EXISTS messages (
                                        id              BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
                                        conversation_id BIGINT       NOT NULL              COMMENT '所属会话ID',
                                        role            VARCHAR(20)  NOT NULL              COMMENT '角色：user / assistant',
                                        content         TEXT         NOT NULL              COMMENT '消息内容',
                                        mode            VARCHAR(20)  DEFAULT 'tutor'       COMMENT '对话模式：tutor / path / resource',
                                        created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                        INDEX idx_conversation_id (conversation_id),
                                        INDEX idx_conversation_mode (conversation_id, mode)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会话消息';

-- 3. 学习计划
CREATE TABLE IF NOT EXISTS learning_plans (
                                              id              BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
                                              user_id         BIGINT       NOT NULL              COMMENT '用户ID',
                                              course_id       VARCHAR(100) DEFAULT ''            COMMENT '课程ID',
                                              title           VARCHAR(255) NOT NULL              COMMENT '计划标题',
                                              status          VARCHAR(20)  NOT NULL DEFAULT 'in_progress' COMMENT '状态：in_progress / completed / paused',
                                              total_steps     INT          NOT NULL DEFAULT 0    COMMENT '总步骤数',
                                              completed_steps INT          NOT NULL DEFAULT 0    COMMENT '已完成步骤数',
                                              created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                              updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                              INDEX idx_user_id (user_id),
                                              INDEX idx_user_status (user_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学习计划';

-- 4. 计划步骤
CREATE TABLE IF NOT EXISTS plan_steps (
                                          id         BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
                                          plan_id    BIGINT       NOT NULL              COMMENT '所属计划ID',
                                          node_id    VARCHAR(100) DEFAULT ''            COMMENT '知识图谱节点ID',
                                          topic      VARCHAR(255) DEFAULT ''            COMMENT '知识点名称',
                                          `order`    INT          NOT NULL DEFAULT 0    COMMENT '排序序号',
                                          status     VARCHAR(20)  NOT NULL DEFAULT 'pending' COMMENT '状态：pending / in_progress / completed / locked',
                                          node_type  VARCHAR(20)  DEFAULT 'learn'       COMMENT '节点类型：learn / practice / review',
                                          depth      INT          DEFAULT 0             COMMENT '图谱深度层级',
                                          created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                          updated_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                          INDEX idx_plan_id (plan_id),
                                          INDEX idx_plan_order (plan_id, `order`),
                                          INDEX idx_node_id (node_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学习计划步骤';

-- 5. 节点掌握度
CREATE TABLE IF NOT EXISTS node_masteries (
                                              id             BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
                                              user_id        BIGINT       NOT NULL              COMMENT '用户ID',
                                              node_id        VARCHAR(100) NOT NULL              COMMENT '知识图谱节点ID',
                                              course_id      VARCHAR(100) DEFAULT ''            COMMENT '课程ID',
                                              mastery        FLOAT        DEFAULT 0.0           COMMENT '掌握度 (0.0-1.0)',
                                              review_count   INT          DEFAULT 0             COMMENT '复习次数',
                                              last_review_at DATETIME                           COMMENT '最近复习时间',
                                              created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                              updated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                              INDEX idx_user_course (user_id, course_id),
                                              UNIQUE KEY uk_user_node (user_id, node_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='节点掌握度';

-- 6. 学习活动记录
CREATE TABLE IF NOT EXISTS learning_activities (
                                                   id               BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
                                                   user_id          BIGINT       NOT NULL              COMMENT '用户ID',
                                                   plan_id          BIGINT                             COMMENT '所属计划ID',
                                                   step_id          BIGINT                             COMMENT '所属步骤ID',
                                                   activity_type    VARCHAR(20)  NOT NULL              COMMENT '活动类型：exercise / review / study',
                                                   duration_minutes INT          DEFAULT 0             COMMENT '耗时（分钟）',
                                                   score            FLOAT        DEFAULT NULL          COMMENT '得分 (0.0-1.0)',
                                                   created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                                   INDEX idx_user_id (user_id),
                                                   INDEX idx_user_plan (user_id, plan_id),
                                                   INDEX idx_user_created (user_id, created_at DESC),
                                                   INDEX idx_user_type (user_id, activity_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学习活动记录';
