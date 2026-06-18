package com.university.university.learning.dto;

import lombok.Data;

/**
 * 练习生成请求 DTO（仅含前端传入字段，student_profile 由 Java 从 DB 注入）
 */
@Data
public class ExerciseGenRequest {
    /** 题目主题（与 knowledge_node_id 二选一，knowledge_node_id 优先） */
    private String topic;
    /** 知识图谱节点ID（优先于topic） */
    private String knowledge_node_id;
    /** 出题策略：weakness(薄弱点)/review(错题同类)/new(新题) */
    private String strategy;
    /** 题目数量，默认 3，范围 1-20 */
    private Integer count;
    /** 难度：easy / medium / hard，默认 medium */
    private String difficulty;
}
