package com.university.university.learning.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.university.learning.entity.Conversation;

import java.util.List;

/**
 * 对话会话服务接口
 */
public interface IConversationService extends IService<Conversation> {

    /** 根据用户ID查询会话列表 */
    List<Conversation> listByUserId(Long userId);

    /** 获取用户当前活跃的会话 */
    Conversation getActiveByUserId(Long userId);
}
