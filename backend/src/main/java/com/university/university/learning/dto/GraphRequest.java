package com.university.university.learning.dto;

import lombok.Data;

/**
 * 图谱通用请求 DTO（next-node / progress / check-prerequisites / export-mermaid / layered 共用）
 */
@Data
public class GraphRequest {
    /** 课程ID */
    private String course_id;
    /** 节点ID（check-prerequisites 使用） */
    private String node_id;
    /** 前置条件阈值（check-prerequisites 使用，默认0.6） */
    private Double threshold;
}
