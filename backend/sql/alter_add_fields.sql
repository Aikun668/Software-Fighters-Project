-- =============================================
-- 节点功能补字段 DDL
-- =============================================

-- LearningPlan 增加字段
ALTER TABLE learning_plans
    ADD COLUMN last_activity_at DATETIME COMMENT '最近活动时间（用于软着陆算法）' AFTER completed_steps,
    ADD COLUMN paused_at        DATETIME COMMENT '暂停时间' AFTER last_activity_at;

-- PlanStep 增加字段（所有计划算法都依赖这些字段）
ALTER TABLE plan_steps
    ADD COLUMN topic_difficulty INT   DEFAULT 3   COMMENT '知识点难度 (1-5)' AFTER depth,
    ADD COLUMN mastery_current  FLOAT DEFAULT 0.0 COMMENT '当前掌握度 (0.0-1.0)' AFTER topic_difficulty,
    ADD COLUMN mastery_after    FLOAT DEFAULT 0.0 COMMENT '更新后掌握度' AFTER mastery_current,
    ADD COLUMN review_count     INT   DEFAULT 0   COMMENT '复习次数' AFTER mastery_after,
    ADD COLUMN last_review_at   DATETIME          COMMENT '最近复习时间' AFTER review_count,
    ADD COLUMN estimated_days   INT   DEFAULT 1   COMMENT '预计学习天数' AFTER last_review_at;
