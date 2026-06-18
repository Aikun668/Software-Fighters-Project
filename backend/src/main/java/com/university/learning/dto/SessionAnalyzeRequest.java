package com.university.learning.dto;

import lombok.Data;
import java.util.List;
import java.util.Map;

/**
 * 练习会话分析请求 DTO
 */
@Data
public class SessionAnalyzeRequest {
    /** 答题记录列表 */
    private List<Map<String, Object>> records;
    /** 课程ID */
    private String course_id;
}
