package com.university.university.learning.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.university.learning.entity.LearningActivity;

import java.util.List;
import java.util.Map;

/**
 * 学习活动记录服务接口
 */
public interface ILearningActivityService extends IService<LearningActivity> {

    /** 获取最近的学习活动记录列表（含topic关联） */
    List<Map<String, Object>> listRecentWithTopic(Long userId, int limit);

    /** 获取用户学习活动统计摘要 */
    Map<String, Object> getStats(Long userId);

    /** 获取用户得分趋势（按日期聚合） */
    List<Map<String, Object>> getScoreTrend(Long userId, int days);

    /** 获取用户总练习次数 */
    Long countExercises(Long userId);

    /** 获取连续学习天数 */
    int getConsecutiveDays(Long userId);

    /** 获取总学习时长（分钟） */
    int getTotalMinutes(Long userId);
}
