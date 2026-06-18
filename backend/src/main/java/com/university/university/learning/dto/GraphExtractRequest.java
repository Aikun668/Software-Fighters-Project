package com.university.university.learning.dto;

import lombok.Data;

import java.util.List;

/**
 * 图谱提取请求 DTO
 */
@Data
public class GraphExtractRequest {
    /** 课程ID */
    private String course_id;
    /** 用户消息 */
    private String user_message;
    /** AI助手回复 */
    private String assistant_reply;
    /** 已存在的节点ID列表 */
    private List<String> existing_node_ids;
}
