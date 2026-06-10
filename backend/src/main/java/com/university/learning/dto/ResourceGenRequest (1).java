package com.university.learning.dto;

import lombok.Data;
import java.util.Map;

@Data
public class ResourceGenRequest {
    private Long user_id;
    private String topic;
    private Map<String, Object> student_profile;
}