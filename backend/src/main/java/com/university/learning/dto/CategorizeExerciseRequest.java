package com.university.learning.dto;

import lombok.Data;
import java.util.List;
import java.util.Map;

/**
 * 练习题分类请求 DTO
 */
@Data
public class CategorizeExerciseRequest {
    /** 练习题列表 */
    private List<Map<String, Object>> exercises;
    /** 知识图谱节点列表 */
    private List<Map<String, Object>> knowledge_nodes;
    /** 课程ID */
    private String course_id;
}
