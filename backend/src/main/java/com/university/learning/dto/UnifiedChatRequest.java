package com.university.learning.dto;

import lombok.Data;
import java.util.List;

/**
 * 统一对话入口请求 DTO（仅含前端传入字段，student_profile/messages 由 Java 从 DB 注入）
 */
@Data
public class UnifiedChatRequest {
    /** 用户自然语言输入（必填） */
    private String message;
    /** 对话模式：auto(默认)/plan/resource/exercise，不传默认 auto */
    private String mode;
    /** 会话ID（续接对话时传入，不传则自动创建新会话） */
    private Long conversation_id;
    /** 用户上传的图片URL列表（可选，多模态输入） */
    private List<String> images;
    /**
     * 本轮图片对应的 file_info.id 列表（可选）。
     *
     * 与 images 一一对应，用于把图片**持久化**到消息表：
     * images 里是 7 天过期的预签名 URL，不能存；存 id 才能在历史回读时重新签发。
     */
    private List<Long> image_file_ids;
    /** 答疑风格：standard(标准) / socratic(苏格拉底式引导)，仅答疑场景生效 */
    private String style;
}
