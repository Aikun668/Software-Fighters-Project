package com.university.learning.dto;

import lombok.Data;
import java.util.List;

@Data
public class GradeRequest {
    private String type;           // choice / short_answer
    private String user_answer;
    private String correct_answer;
    private List<String> choices;
    private Boolean multi;         // 是否多选题
    private Integer points;        // 分值
    private String reference_answer;
    private String rubric;
}