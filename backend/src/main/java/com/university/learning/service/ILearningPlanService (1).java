package com.university.learning.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.university.learning.entity.LearningPlan;

import java.util.List;

/**
 * 学习计划服务接口
 */
public interface ILearningPlanService extends IService<LearningPlan> {

    /** 根据用户ID查询学习计划列表 */
    List<LearningPlan> listByUserId(Long userId);

    /** 获取用户当前进行中的学习计划 */
    LearningPlan getActiveByUserId(Long userId);
}
