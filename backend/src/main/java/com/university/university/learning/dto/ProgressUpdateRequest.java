package com.university.university.learning.dto;

import lombok.Data;

/**
 * 计划进度更新请求 DTO（user_id 由 Java 从 JWT 注入）
 */
@Data
public class ProgressUpdateRequest {
    /** 步骤ID */
    private Long step_id;
    /** 步骤排序号 */
    private Integer step_order;
    /** 新状态：pending / in_progress / completed */
    private String status;
    /** 活动类型：exercise / quiz / resource_viewed */
    private String activity_type;
    /** 得分 */
    private Float score;
    /** 学习时长（分钟） */
    private Integer duration_minutes;
}
