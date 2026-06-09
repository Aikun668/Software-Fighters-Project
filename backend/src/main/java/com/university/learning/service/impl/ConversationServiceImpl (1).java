package com.university.learning.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.university.learning.entity.Conversation;
import com.university.learning.mapper.ConversationMapper;
import com.university.learning.service.IConversationService;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * 对话会话服务实现
 */
@Service
public class ConversationServiceImpl extends ServiceImpl<ConversationMapper, Conversation> implements IConversationService {

    @Override
    public List<Conversation> listByUserId(Long userId) {
        return this.list(
                new LambdaQueryWrapper<Conversation>()
                        .eq(Conversation::getUserId, userId)
                        .orderByDesc(Conversation::getUpdatedAt)
        );
    }

    @Override
    public Conversation getActiveByUserId(Long userId) {
        return this.getOne(
                new LambdaQueryWrapper<Conversation>()
                        .eq(Conversation::getUserId, userId)
                        .eq(Conversation::getStatus, "active")
                        .orderByDesc(Conversation::getUpdatedAt)
                        .last("LIMIT 1")
        );
    }
}
