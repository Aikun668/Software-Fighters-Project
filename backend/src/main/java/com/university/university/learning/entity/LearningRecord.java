package com.university.university.learning.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("learning_records")
public class LearningRecord {
    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;
    private Long resourceId;

    private Float progress;      // 完成进度 0-100
    private Float score;         // 得分
    private Integer timeSpent;   // 学习时长(秒)

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}