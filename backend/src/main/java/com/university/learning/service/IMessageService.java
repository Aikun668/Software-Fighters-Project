package com.university.learning.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.university.learning.entity.Message;

import java.util.List;

/**
 * 会话消息服务接口
 */
public interface IMessageService extends IService<Message> {

    /** 按会话ID查询全部消息 */
    List<Message> listByConversationId(Long conversationId);

    /** 最近消息，时间与ID降序；调用方可反转为时间线。 */
    List<Message> listRecentByConversationId(Long conversationId, int limit);

    /** 按会话ID和模式查询消息（用于加载历史） */
    List<Message> listByConversationIdAndMode(Long conversationId, String mode, int limit);

    /** 原始分页查询消息（不按模式过滤，用于压缩/摘要场景） */
    List<Message> listByConversationIdRaw(Long conversationId, int offset, int limit);

    /** 批量保存用户消息和AI回复（一个事务内完成2条INSERT） */
    int saveMessages(Long conversationId, String userMessage, String assistantMessage,
                     String userMode, String assistantMode);
}
