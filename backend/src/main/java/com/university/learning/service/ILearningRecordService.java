package com.university.learning.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.university.learning.entity.LearningRecord;

import java.util.List;

public interface ILearningRecordService extends IService<LearningRecord> {

    /**
     * 保存或更新学习进度
     */
    LearningRecord saveOrUpdateProgress(LearningRecord record);

    /**
     * 获取用户所有学习记录
     */
    List<LearningRecord> listByUserId(Long userId);

    /**
     * 根据用户和资源获取学习记录
     */
    LearningRecord getByUserAndResource(Long userId, Long resourceId);

    /**
     * 获取用户某类资源的学习记录
     */
    List<LearningRecord> listByUserIdAndType(Long userId, String resourceType);

    /**
     * 统计用户总得分
     */
    Float getTotalScore(Long userId);

    /**
     * 统计用户平均分
     */
    Float getAverageScore(Long userId);
}