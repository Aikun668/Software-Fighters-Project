package com.university.learning.dto;

import lombok.Data;
import java.util.List;
import java.util.Map;

@Data
public class TutorChatRequest {
    private Long user_id;
    private Map<String, Object> student_profile;

    // 新API
    private String content;
    private String conversation_id;

    // 旧API（向后兼容）
    private List<Map<String, String>> messages;
}