package com.university.learning.entity;


import com.baomidou.mybatisplus.annotation.*;
import com.baomidou.mybatisplus.extension.handlers.JacksonTypeHandler;
import lombok.Data;
import java.time.LocalDateTime;

@Data
@TableName(value = "student_profiles", autoResultMap = true)
public class StudentProfile {
    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;

    // 6维画像
    private Integer knowledgeBase;      // 知识基础 0-100
    private String cognitiveStyle;      // 认知风格: visual/auditory/kinesthetic/theoretical
    private String learningGoal;        // 学习目标

    @TableField(typeHandler = JacksonTypeHandler.class)
    private Object weakPoints;          // 易错点列表 JSON

    private String learningPace;        // 学习节奏: fast/steady/slow

    @TableField(typeHandler = JacksonTypeHandler.class)
    private Object interestDirection;   // 兴趣方向 JSON

    @TableField(typeHandler = JacksonTypeHandler.class)
    private Object rawProfileJson;      // 完整画像快照 JSON

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}