package com.university.learning.dto;

import lombok.Data;
import java.util.Map;

@Data
public class ExerciseGenRequest {
    private Long user_id;
    private String topic;
    private Integer count;
    private String difficulty;
    private Map<String, Object> student_profile;
}