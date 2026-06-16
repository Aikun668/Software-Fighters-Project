package com.university.learning.dto;

import lombok.Data;
import java.util.List;
import java.util.Map;

/**
 * 对话辅导请求 DTO（仅含前端传入字段，student_profile 和 messages 由 Java 从 DB 注入）
 */
@Data
public class TutorChatRequest {
    /** 用户当前输入的消息内容 */
    private String content;
    /** 会话ID（续接对话时传入） */
    private Long conversation_id;
    /** 当前轮次用户刚发的消息列表（前端传最新消息，Java 合并历史后传给 Python） */
    private List<Map<String, String>> messages;
}
