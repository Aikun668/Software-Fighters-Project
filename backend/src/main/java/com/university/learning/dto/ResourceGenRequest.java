package com.university.learning.dto;

import lombok.Data;

/**
 * 资源生成请求 DTO（仅含前端传入字段，student_profile 由 Java 从 DB 注入）
 */
@Data
public class ResourceGenRequest {
    /** 资源主题（必填） */
    private String topic;
    /** 资源类型：document/code/project/mindmap/flashcard/interactive_diagram，不传由AI自动判断 */
    private String resource_type;
}
