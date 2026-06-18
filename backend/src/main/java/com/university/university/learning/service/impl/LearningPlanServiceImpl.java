package com.university.university.learning.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.university.learning.entity.LearningPlan;
import com.university.learning.mapper.LearningPlanMapper;
import com.university.learning.service.ILearningPlanService;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * 学习计划服务实现
 */
@Service
public class LearningPlanServiceImpl extends ServiceImpl<LearningPlanMapper, LearningPlan> implements ILearningPlanService {

    @Override
    public List<LearningPlan> listByUserId(Long userId) {
        return this.list(
                new LambdaQueryWrapper<LearningPlan>()
                        .eq(LearningPlan::getUserId, userId)
                        .orderByDesc(LearningPlan::getUpdatedAt)
        );
    }

    @Override
    public LearningPlan getActiveByUserId(Long userId) {
        return this.getOne(
                new LambdaQueryWrapper<LearningPlan>()
                        .eq(LearningPlan::getUserId, userId)
                        .eq(LearningPlan::getStatus, "in_progress")
                        .orderByDesc(LearningPlan::getUpdatedAt)
                        .last("LIMIT 1")
        );
    }
}
