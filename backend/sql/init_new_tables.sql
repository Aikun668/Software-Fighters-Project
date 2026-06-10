-- =============================================
-- 学习平台 6 张新表 DDL（MySQL）
-- =============================================

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
