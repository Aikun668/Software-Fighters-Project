package com.university.university.learning.dto;

import lombok.Data;

/**
 * 解题请求 DTO（user_id 由 Java 从 JWT 注入）
 */
@Data
public class SolveRequest {
    /** 需要解答的问题（必填） */
    private String question;
    /** 知识库上下文（可选） */
    private String context;
}
