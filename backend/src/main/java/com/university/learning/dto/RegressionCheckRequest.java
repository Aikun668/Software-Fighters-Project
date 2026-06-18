package com.university.learning.dto;

import lombok.Data;
import java.util.List;
import java.util.Map;

/**
 * 回归检测请求 DTO（user_id 由 Java 从 JWT 注入）
 */
@Data
public class RegressionCheckRequest {
    /** 用户答案列表（阶段2传，阶段1不传） */
    private List<Map<String, Object>> answers;
    /** 计划空闲天数 */
    private Integer days_idle;
}
