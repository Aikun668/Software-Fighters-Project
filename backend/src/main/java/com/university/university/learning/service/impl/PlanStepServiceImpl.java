package com.university.university.learning.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.university.learning.entity.PlanStep;
import com.university.learning.mapper.PlanStepMapper;
import com.university.learning.service.IPlanStepService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

/**
 * 学习计划步骤服务实现
 */
@Service
public class PlanStepServiceImpl extends ServiceImpl<PlanStepMapper, PlanStep> implements IPlanStepService {

    @Override
    public List<PlanStep> listByPlanId(Long planId) {
        return this.list(
                new LambdaQueryWrapper<PlanStep>()
                        .eq(PlanStep::getPlanId, planId)
                        .orderByAsc(PlanStep::getOrder)
        );
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void shiftAfterOrder(Long planId, int afterOrder) {
        // 查询order大于指定值的所有步骤
        List<PlanStep> steps = this.list(
                new LambdaQueryWrapper<PlanStep>()
                        .eq(PlanStep::getPlanId, planId)
                        .gt(PlanStep::getOrder, afterOrder)
        );
        // 每个步骤order+1
        for (PlanStep step : steps) {
            step.setOrder(step.getOrder() + 1);
        }
        this.updateBatchById(steps);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public List<Long> lockSuccessors(Long planId, String nodeId) {
        List<PlanStep> allSteps = this.listByPlanId(planId);

        // 找到目标节点之后的所有步骤并锁定
        boolean found = false;
        for (PlanStep step : allSteps) {
            if (found) {
                step.setStatus("locked");
            }
            if (step.getNodeId().equals(nodeId)) {
                found = true;
            }
        }

        List<PlanStep> toUpdate = allSteps.stream()
                .filter(s -> "locked".equals(s.getStatus()))
                .collect(Collectors.toList());

        if (!toUpdate.isEmpty()) {
            this.updateBatchById(toUpdate);
        }

        return toUpdate.stream().map(PlanStep::getId).collect(Collectors.toList());
    }
}
