package com.university.learning.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.experimental.Accessors;

import java.time.LocalDateTime;

/**
 * 学习活动记录实体
 */
@Data
@Accessors(chain = true)
@TableName("learning_activities")
public class LearningActivity {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 用户ID */
    private Long userId;

    /** 所属学习计划ID */
    private Long planId;

    /** 所属步骤ID */
    private Long stepId;

    /** 活动类型：exercise / review / study */
    private String activityType;

    /** 耗时（分钟） */
    private Integer durationMinutes;

    /** 得分 (0.0 ~ 1.0) */
    private Float score;

    /** 创建时间 */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}
