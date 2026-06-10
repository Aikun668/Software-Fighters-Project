package com.university.learning.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.university.learning.entity.Conversation;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface ConversationMapper extends BaseMapper<Conversation> {
}