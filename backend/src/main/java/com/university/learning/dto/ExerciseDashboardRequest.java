package com.university.learning.dto;

import lombok.Data;
import java.util.List;
import java.util.Map;

/**
 * 练习仪表盘请求 DTO（user_id 由 Java 从 JWT 注入）
 */
@Data
public class ExerciseDashboardRequest {
    /** 最近练习记录 */
    private List<Map<String, Object>> recent_records;
    /** 课程ID */
    private String course_id;
}
