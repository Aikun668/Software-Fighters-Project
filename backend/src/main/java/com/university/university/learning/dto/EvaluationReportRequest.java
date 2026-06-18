package com.university.university.learning.dto;

import lombok.Data;

import java.util.Map;

/**
 * 评估报告请求 DTO（user_id 由 Java 从 JWT 注入）
 */
@Data
public class EvaluationReportRequest {
    /** 答题评估结果 */
    private Map<String, Object> evaluation_results;
}
