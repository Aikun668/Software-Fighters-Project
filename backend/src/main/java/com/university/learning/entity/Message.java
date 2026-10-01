package com.university.learning.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.baomidou.mybatisplus.extension.handlers.JacksonTypeHandler;
import lombok.Data;
import lombok.experimental.Accessors;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 会话消息实体
 */
@Data
@Accessors(chain = true)
@TableName(value = "messages", autoResultMap = true)
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

    /**
     * 本条消息附带的图片，存 file_info.id 列表。
     *
     * 存 id 而不是预签名 URL：URL 只有 7 天有效期，
     * 直接存 URL 会让历史图片过一阵必然失效（403）。
     * 回读时用 id 重新签发即可。
     */
    @TableField(typeHandler = JacksonTypeHandler.class)
    private List<Long> imageFileIds;

    /**
     * 回读时临时填充的图片可访问 URL（不落库）。
     * 由 ConversationController 用 imageFileIds 重新签名得到。
     */
    @TableField(exist = false)
    private List<String> images;

    /** 创建时间 */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}
