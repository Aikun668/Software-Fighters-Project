package com.university.learning.dto;

import lombok.Data;
import java.util.List;
import java.util.Map;

@Data
public class ProfileChatRequest {
    private Long user_id;
    private List<Map<String, String>> messages;
}