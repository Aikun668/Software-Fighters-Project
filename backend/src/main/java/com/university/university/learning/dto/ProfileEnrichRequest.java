package com.university.university.learning.dto;

import lombok.Data;

import java.util.List;
import java.util.Map;

/**
 * 练习画像增强请求 DTO（user_id/student_profile 由 Java 从 DB 注入）
 */
@Data
public class ProfileEnrichRequest {
    /** 最近练习记录 */
    private List<Map<String, Object>> recent_records;
    /** 会话分析结果 */
    private Map<String, Object> session_analysis;
}
