package com.university.learning.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.experimental.Accessors;

import java.time.LocalDateTime;

/**
 * 学习计划步骤实体
 */
@Data
@Accessors(chain = true)
@TableName("plan_steps")
public class PlanStep {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 所属计划ID */
    private Long planId;

    /** 知识图谱节点ID */
    private String nodeId;

    /** 知识点名称 */
    private String topic;

    /** 排序序号（从0开始） */
    @TableField("`order`")
    private Integer order;

    /** 状态：pending / in_progress / completed / locked */
    private String status;

    /** 节点类型：learn / practice / review */
    private String nodeType;

    /** 图谱深度层级 */
    private Integer depth;

    /** 创建时间 */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    /** 更新时间 */
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}
