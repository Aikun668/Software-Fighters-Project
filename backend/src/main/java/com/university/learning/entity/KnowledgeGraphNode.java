package com.university.learning.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.baomidou.mybatisplus.extension.handlers.JacksonTypeHandler;
import lombok.Data;
import lombok.experimental.Accessors;

/**
 * 知识图谱节点
 */
@Data
@Accessors(chain = true)
@TableName(value = "knowledge_graph_nodes", autoResultMap = true)
public class KnowledgeGraphNode {

    @TableId(type = IdType.INPUT)
    private String id;

    /** 节点名称 */
    private String name;

    /** 节点描述 */
    private String description;

    /** 难度 1-5 */
    private Integer difficulty;

    /** 分类：基础/ML/DL/NLP/LLM */
    private String category;

    /** 课程ID */
    private String courseId;

    /** 子概念列表（JSON） */
    @TableField(typeHandler = JacksonTypeHandler.class)
    private Object subConcepts;
}
