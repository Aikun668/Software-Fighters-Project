package com.university.learning.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.university.learning.entity.PlanStep;

import java.util.List;

/**
 * 学习计划步骤服务接口
 */
public interface IPlanStepService extends IService<PlanStep> {

    /** 按计划ID查询步骤列表（按order排序） */
    List<PlanStep> listByPlanId(Long planId);

    /** 将指定order之后的所有步骤order+1（用于中间插入步骤时腾出空位） */
    void shiftAfterOrder(Long planId, int afterOrder);

    /** 锁定指定节点之后的所有后继步骤 */
    List<Long> lockSuccessors(Long planId, String nodeId);
}
