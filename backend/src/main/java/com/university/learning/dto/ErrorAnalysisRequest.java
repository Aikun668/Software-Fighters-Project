package com.university.learning.dto;

import lombok.Data;
import java.util.List;
import java.util.Map;

/**
 * 错题分析请求 DTO
 */
@Data
public class ErrorAnalysisRequest {
    /** 错题列表 [{question, user_answer, correct_answer}] */
    private List<Map<String, Object>> errors;
    /** 学生水平 1-5 */
    private int level;
}
