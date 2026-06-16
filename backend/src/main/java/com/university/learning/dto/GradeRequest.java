package com.university.learning.dto;

import lombok.Data;
import java.util.List;

/**
 * 练习批改请求 DTO
 */
@Data
public class GradeRequest {
    /** 题目类型：choice / short_answer / code */
    private String type;
    /** 用户答案 */
    private String user_answer;
    /** 正确答案（选择题） */
    private String correct_answer;
    /** 选项列表 */
    private List<String> choices;
    /** 是否多选题 */
    private Boolean multi;
    /** 分值 */
    private Integer points;
    /** 参考答案（简答题/代码题） */
    private String reference_answer;
    /** 评分标准（简答题/代码题） */
    private String rubric;
    /** 关联的资源ID（Java落库用） */
    private Long resource_id;
}