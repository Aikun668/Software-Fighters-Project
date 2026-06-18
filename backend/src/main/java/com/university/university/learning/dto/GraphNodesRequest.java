package com.university.university.learning.dto;

import lombok.Data;

import java.util.List;
import java.util.Map;

/**
 * 图谱节点更新请求 DTO
 */
@Data
public class GraphNodesRequest {
    /** 课程ID */
    private String course_id;
    /** 节点/边更新列表 [{action: "add_node"|"add_edge", data: {...}}] */
    private List<Map<String, Object>> updates;
}
