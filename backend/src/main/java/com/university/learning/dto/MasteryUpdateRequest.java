package com.university.learning.dto;

import lombok.Data;
import java.util.List;
import java.util.Map;

/**
 * 掌握度批量更新请求 DTO
 */
@Data
public class MasteryUpdateRequest {
    /** 课程ID */
    private String course_id;
    /** 学习事件列表 [{node_id, event_type, score}] */
    private List<Map<String, Object>> events;
}
