package com.university.learning.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.university.learning.entity.Message;
import com.university.learning.mapper.MessageMapper;
import com.university.learning.service.IMessageService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 会话消息服务实现
 */
@Service
public class MessageServiceImpl extends ServiceImpl<MessageMapper, Message> implements IMessageService {

    @Override
    public List<Message> listByConversationId(Long conversationId) {
        return this.list(
                new LambdaQueryWrapper<Message>()
                        .eq(Message::getConversationId, conversationId)
                        .orderByAsc(Message::getCreatedAt)
        );
    }

    @Override
    public List<Message> listRecentByConversationId(Long conversationId, int limit) {
        int bounded = Math.max(1, Math.min(limit, 501));
        return this.list(new LambdaQueryWrapper<Message>()
                .eq(Message::getConversationId, conversationId)
                .orderByDesc(Message::getCreatedAt).orderByDesc(Message::getId)
                .last("LIMIT " + bounded));
    }

    @Override
    public List<Message> listByConversationIdAndMode(Long conversationId, String mode, int limit) {
        return this.list(
                new LambdaQueryWrapper<Message>()
                        .eq(Message::getConversationId, conversationId)
                        .eq(Message::getMode, mode)
                        .orderByAsc(Message::getCreatedAt)
                        .last("LIMIT " + limit)
        );
    }

    @Override
    public List<Message> listByConversationIdRaw(Long conversationId, int offset, int limit) {
        return this.list(
                new LambdaQueryWrapper<Message>()
                        .eq(Message::getConversationId, conversationId)
                        .orderByAsc(Message::getCreatedAt)
                        .last("LIMIT " + offset + ", " + limit)
        );
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public int saveMessages(Long conversationId, String userMessage, String assistantMessage,
                            String userMode, String assistantMode) {
        LocalDateTime now = LocalDateTime.now();

        Message userMsg = new Message()
                .setConversationId(conversationId)
                .setRole("user")
                .setContent(userMessage)
                .setMode(userMode)
                .setCreatedAt(now);

        Message assistantMsg = new Message()
                .setConversationId(conversationId)
                .setRole("assistant")
                .setContent(assistantMessage)
                .setMode(assistantMode)
                .setCreatedAt(now);

        // 一个事务内完成2条INSERT
        this.saveBatch(List.of(userMsg, assistantMsg));
        return 2;
    }
}
