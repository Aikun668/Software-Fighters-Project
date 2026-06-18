package com.university.university.learning.mapper;


import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.university.learning.entity.LearningRecord;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface LearningRecordMapper extends BaseMapper<LearningRecord> {
}