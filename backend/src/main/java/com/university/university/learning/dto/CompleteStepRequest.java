package com.university.university.learning.dto;

import lombok.Data;

import java.util.Map;

/**
 * 步骤完成巩固请求 DTO
 */
@Data
public class CompleteStepRequest {
    /** 完成的步骤数据 */
    private Map<String, Object> step;
}
