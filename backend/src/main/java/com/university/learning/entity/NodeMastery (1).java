package com.university.learning.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.experimental.Accessors;

import java.time.LocalDateTime;

/**
 * 知识图谱节点掌握度实体
 */
@Data
@Accessors(chain = true)
@TableName("node_masteries")
public class NodeMastery {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 用户ID */
    private Long userId;

    /** 知识图谱节点ID */
    private String nodeId;

    /** 课程ID */
    private String courseId;

    /** 掌握度 (0.0 ~ 1.0) */
    private Float mastery;

    /** 复习次数 */
    private Integer reviewCount;

    /** 最近复习时间 */
    private LocalDateTime lastReviewAt;

    /** 创建时间 */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    /** 更新时间 */
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}
