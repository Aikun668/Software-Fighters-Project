package com.university.university.learning.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.experimental.Accessors;

/**
 * 知识图谱边
 */
@Data
@Accessors(chain = true)
@TableName("knowledge_graph_edges")
public class KnowledgeGraphEdge {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 源节点ID */
    private String source;

    /** 目标节点ID */
    private String target;

    /** 关系类型：depends_on / extends / parallel */
    private String relation;

    /** 关系说明 */
    private String rationale;

    /** 课程ID */
    private String courseId;
}
