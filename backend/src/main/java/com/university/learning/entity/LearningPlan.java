package com.university.learning.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.experimental.Accessors;

import java.time.LocalDateTime;

/**
 * 学习计划实体
 */
@Data
@Accessors(chain = true)
@TableName("learning_plans")
public class LearningPlan {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 用户ID */
    private Long userId;

    /** 课程ID */
    private String courseId;

    /** 计划标题 */
    private String title;

    /** 状态：in_progress / completed / paused */
    private String status;

    /** 总步骤数 */
    private Integer totalSteps;

    /** 已完成步骤数 */
    private Integer completedSteps;

    /** 最近活动时间（用于软着陆算法计算idle天数） */
    private LocalDateTime lastActivityAt;

    /** 暂停时间 */
    private LocalDateTime pausedAt;

    /** 创建时间 */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    /** 更新时间 */
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}