package com.university.university.learning.dto;

import lombok.Data;

import java.util.List;
import java.util.Map;

/**
 * 创建学习计划请求 DTO（user_id 由 Java 从 JWT 注入）
 */
@Data
public class CreatePlanRequest {
    /** 课程ID */
    private String course_id;
    /** 计划标题 */
    private String title;
    /** 计划步骤列表 */
    private List<Map<String, Object>> steps;
}
