package com.university.university.learning.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.experimental.Accessors;

import java.time.LocalDateTime;

/**
 * 会话消息实体
 */
@Data
@Accessors(chain = true)
@TableName("messages")
public class Message {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 所属会话ID */
    private Long conversationId;

    /** 角色：user / assistant */
    private String role;

    /** 消息内容 */
    private String content;

    /** 对话模式：tutor / path / resource */
    private String mode;

    /** 创建时间 */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}