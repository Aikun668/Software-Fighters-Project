package com.university.university.learning.dto;

import lombok.Data;

import java.util.List;
import java.util.Map;

/**
 * 画像对话请求 DTO（user_id 由 Java 从 JWT 注入）
 */
@Data
public class ProfileChatRequest {
    /** 当前轮次对话消息 [{role, content}] */
    private List<Map<String, String>> messages;
}
