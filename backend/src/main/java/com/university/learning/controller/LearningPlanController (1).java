package com.university.learning.controller;

import com.university.learning.common.Result;
import com.university.learning.entity.LearningPlan;
import com.university.learning.entity.PlanStep;
import com.university.learning.service.ILearningPlanService;
import com.university.learning.service.IPlanStepService;
import lombok.RequiredArgsConstructor;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 学习计划与步骤接口
 */
@RestController
@RequiredArgsConstructor
public class LearningPlanController {

    private final ILearningPlanService planService;
    private final IPlanStepService stepService;

    /** 创建学习计划（含步骤列表） */
    @PostMapping("/api/plans")
    @Transactional(rollbackFor = Exception.class)
    public Result createPlan(@RequestBody Map<String, Object> body) {
        Long userId = Long.valueOf(body.get("user_id").toString());
        String courseId = (String) body.get("course_id");
        String title = (String) body.get("title");

        LearningPlan plan = new LearningPlan()
                .setUserId(userId)
                .setCourseId(courseId)
                .setTitle(title)
                .setStatus("in_progress");

        @SuppressWarnings("unchecked")
        List<Map<String, Object>> stepsData = (List<Map<String, Object>>) body.get("steps");

        int totalSteps = stepsData != null ? stepsData.size() : 0;
        plan.setTotalSteps(totalSteps);
        plan.setCompletedSteps(0);
        planService.save(plan);

        // 批量创建步骤
        if (stepsData != null) {
            for (Map<String, Object> stepData : stepsData) {
                PlanStep step = new PlanStep()
                        .setPlanId(plan.getId())
                        .setNodeId((String) stepData.get("node_id"))
                        .setTopic((String) stepData.get("topic"))
                        .setOrder(toInt(stepData.get("order"), 0))
                        .setStatus((String) stepData.getOrDefault("status", "pending"))
                        .setNodeType((String) stepData.getOrDefault("node_type", "learn"))
                        .setDepth(toInt(stepData.get("depth"), 0));
                stepService.save(step);
            }
        }

        // 返回含步骤列表的计划
        plan.setTotalSteps(totalSteps);
        List<PlanStep> steps = stepService.listByPlanId(plan.getId());
        Map<String, Object> result = Map.of(
                "id", plan.getId(),
                "user_id", plan.getUserId(),
                "course_id", plan.getCourseId(),
                "title", plan.getTitle(),
                "status", plan.getStatus(),
                "total_steps", plan.getTotalSteps(),
                "completed_steps", plan.getCompletedSteps(),
                "steps", steps
        );
        return Result.ok(result);
    }

    /** 获取计划详情（含步骤列表） */
    @GetMapping("/api/plans/{id}")
    public Result getPlan(@PathVariable Long id, @RequestParam Long userId) {
        LearningPlan plan = planService.getById(id);
        if (plan == null) {
            return Result.fail(404, "计划不存在");
        }
        List<PlanStep> steps = stepService.listByPlanId(id);
        Map<String, Object> result = Map.of(
                "id", plan.getId(),
                "user_id", plan.getUserId(),
                "course_id", plan.getCourseId(),
                "title", plan.getTitle(),
                "status", plan.getStatus(),
                "total_steps", plan.getTotalSteps(),
                "completed_steps", plan.getCompletedSteps(),
                "steps", steps
        );
        return Result.ok(result);
    }

    /** 更新计划 */
    @PutMapping("/api/plans/{id}")
    public Result updatePlan(@PathVariable Long id, @RequestBody Map<String, Object> body) {
        LearningPlan plan = planService.getById(id);
        if (plan == null) {
            return Result.fail(404, "计划不存在");
        }
        if (body.containsKey("title")) plan.setTitle((String) body.get("title"));
        if (body.containsKey("status")) plan.setStatus((String) body.get("status"));
        planService.updateById(plan);
        return Result.ok(plan);
    }

    /** 获取计划的所有步骤 */
    @GetMapping("/api/plans/{planId}/steps")
    public Result getSteps(@PathVariable Long planId) {
        List<PlanStep> steps = stepService.listByPlanId(planId);
        return Result.ok(steps);
    }

    /** 在指定位置插入新步骤 */
    @PostMapping("/api/plans/{planId}/steps")
    public Result insertStep(@PathVariable Long planId, @RequestBody Map<String, Object> body) {
        PlanStep step = new PlanStep()
                .setPlanId(planId)
                .setNodeId((String) body.get("node_id"))
                .setTopic((String) body.get("topic"))
                .setOrder(toInt(body.get("order"), 0))
                .setStatus((String) body.getOrDefault("status", "locked"))
                .setNodeType((String) body.getOrDefault("node_type", "learn"))
                .setDepth(toInt(body.get("depth"), 0));
        stepService.save(step);

        // 更新计划总步骤数
        LearningPlan plan = planService.getById(planId);
        if (plan != null) {
            plan.setTotalSteps(plan.getTotalSteps() + 1);
            planService.updateById(plan);
        }
        return Result.ok(step);
    }

    /** 更新单个步骤 */
    @PutMapping("/api/plan-steps/{stepId}")
    public Result updateStep(@PathVariable Long stepId, @RequestBody Map<String, Object> body) {
        PlanStep step = stepService.getById(stepId);
        if (step == null) {
            return Result.fail(404, "步骤不存在");
        }
        if (body.containsKey("status")) step.setStatus((String) body.get("status"));
        if (body.containsKey("order")) step.setOrder(toInt(body.get("order"), step.getOrder()));
        stepService.updateById(step);
        return Result.ok(step);
    }

    /** 将指定order之后的所有步骤order+1（用于中间插入腾出空位） */
    @PostMapping("/api/plans/{planId}/steps/shift")
    public Result shiftSteps(@PathVariable Long planId, @RequestBody Map<String, Object> body) {
        int afterOrder = toInt(body.get("after_order"), 0);
        stepService.shiftAfterOrder(planId, afterOrder);
        return Result.ok(Map.of("shifted", true));
    }

    /** 锁定指定节点的所有后继步骤 */
    @PostMapping("/api/plans/{planId}/steps/lock-successors")
    public Result lockSuccessors(@PathVariable Long planId, @RequestBody Map<String, Object> body) {
        String nodeId = (String) body.get("node_id");
        List<Long> lockedIds = stepService.lockSuccessors(planId, nodeId);
        return Result.ok(Map.of("locked_ids", lockedIds));
    }

    /** 处理节点状态变更（原子操作：锁定后继 + 腾空位 + 插入复习步骤 + 更新计数） */
    @PostMapping("/api/plans/node-status-change")
    @Transactional(rollbackFor = Exception.class)
    public Result onNodeStatusChange(@RequestBody Map<String, Object> body) {
        Long userId = Long.valueOf(body.get("user_id").toString());
        String nodeId = (String) body.get("node_id");
        String newStatus = (String) body.get("new_status");
        Long planId = body.get("plan_id") != null ? Long.valueOf(body.get("plan_id").toString()) : null;

        // 查找用户当前 in_progress 的计划
        LearningPlan plan;
        if (planId != null) {
            plan = planService.getById(planId);
        } else {
            plan = planService.getActiveByUserId(userId);
        }
        if (plan == null) {
            return Result.fail(404, "没有进行中的学习计划");
        }

        // 查找对应的步骤并更新状态
        List<PlanStep> steps = stepService.listByPlanId(plan.getId());
        Long updatedStepId = null;
        for (PlanStep step : steps) {
            if (step.getNodeId().equals(nodeId)) {
                step.setStatus(newStatus);
                stepService.updateById(step);
                updatedStepId = step.getId();
                break;
            }
        }

        if (updatedStepId == null) {
            return Result.fail(404, "步骤不存在");
        }

        // 锁定后继步骤
        List<Long> lockedStepIds = stepService.lockSuccessors(plan.getId(), nodeId);

        // 腾出空位并插入复习步骤
        stepService.shiftAfterOrder(plan.getId(), 0);
        PlanStep reviewStep = new PlanStep()
                .setPlanId(plan.getId())
                .setNodeId(nodeId + "_review")
                .setTopic("复习")
                .setOrder(1)
                .setStatus("pending")
                .setNodeType("review")
                .setDepth(0);
        stepService.save(reviewStep);

        // 更新计划计数
        if ("completed".equals(newStatus)) {
            plan.setCompletedSteps(plan.getCompletedSteps() + 1);
        }
        plan.setTotalSteps(plan.getTotalSteps() + 1);
        planService.updateById(plan);

        Map<String, Object> result = Map.of(
                "plan_id", plan.getId(),
                "updated_step_id", updatedStepId,
                "locked_step_ids", lockedStepIds,
                "new_review_step_id", reviewStep.getId()
        );
        return Result.ok(result);
    }

    private int toInt(Object value, int defaultValue) {
        if (value instanceof Number) return ((Number) value).intValue();
        if (value instanceof String) return Integer.parseInt((String) value);
        return defaultValue;
    }
}
