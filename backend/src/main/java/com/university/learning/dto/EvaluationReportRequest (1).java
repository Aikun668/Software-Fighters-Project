package com.university.learning.dto;

import lombok.Data;
import java.util.Map;

@Data
public class EvaluationReportRequest {
    private Long user_id;
    private Map<String, Object> evaluation_results;
}