package com.university.university.learning.controller;

import com.university.learning.client.PythonClient;
import com.university.learning.common.Result;
import com.university.learning.dto.CompleteStepRequest;
import com.university.learning.dto.CreatePlanRequest;
import com.university.learning.dto.ProgressUpdateRequest;
import com.university.learning.dto.RegressionCheckRequest;
import com.university.learning.entity.LearningActivity;
import com.university.learning.entity.LearningPlan;
import com.university.learning.entity.NodeMastery;
import com.university.learning.entity.PlanStep;
import com.university.learning.service.ILearningActivityService;
import com.university.learning.service.ILearningPlanService;
import com.university.learning.service.INodeMasteryService;
import com.university.learning.service.IPlanStepService;
import com.university.learning.utils.UserHolder;
import io.swagger.v3.oas.annotations.Operation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Slf4j
@RestController
@RequiredArgsConstructor
public class LearningPlanController {

    private final ILearningPlanService planService;
    private final IPlanStepService stepService;
    private final PythonClient pythonClient;
    private final INodeMasteryService masteryService;
    private final ILearningActivityService activityService;

    @Operation(summary = "创建学习计划", description = "创建计划并批量添加步骤，事务保证原子性")
    @PostMapping("/api/plans")
    @Transactional(rollbackFor = Exception.class)
    public Result createPlan(@RequestBody CreatePlanRequest body) {
        Long userId = UserHolder.getUser().getId();
        String courseId = body.getCourse_id();
        String title = body.getTitle();

        LearningPlan plan = new LearningPlan()
                .setUserId(userId)
                .setCourseId(courseId)
                .setTitle(title)
                .setStatus("in_progress");

        List<Map<String, Object>> stepsData = body.getSteps();

        int totalSteps = stepsData != null ? stepsData.size() : 0;
        plan.setTotalSteps(totalSteps);
        plan.setCompletedSteps(0);
        planService.save(plan);

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

    @Operation(summary = "获取计划详情", description = "返回计划信息及步骤列表")
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

    @Operation(summary = "更新计划", description = "可更新标题、状态(in_progress/completed/paused)")
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

    @Operation(summary = "获取计划步骤列表")
    @GetMapping("/api/plans/{planId}/steps")
    public Result getSteps(@PathVariable Long planId) {
        List<PlanStep> steps = stepService.listByPlanId(planId);
        return Result.ok(steps);
    }

    @Operation(summary = "插入新步骤", description = "在计划中新增一个步骤，并更新计划总步数")
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

        LearningPlan plan = planService.getById(planId);
        if (plan != null) {
            plan.setTotalSteps(plan.getTotalSteps() + 1);
            planService.updateById(plan);
        }
        return Result.ok(step);
    }

    @Operation(summary = "更新步骤", description = "更新步骤状态(pending/in_progress/completed/locked)或排序位置")
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

    @Operation(summary = "步骤排序位移", description = "将指定 order 后的所有步骤 order+1，用于中间插入腾空位")
    @PostMapping("/api/plans/{planId}/steps/shift")
    public Result shiftSteps(@PathVariable Long planId, @RequestBody Map<String, Object> body) {
        int afterOrder = toInt(body.get("after_order"), 0);
        stepService.shiftAfterOrder(planId, afterOrder);
        return Result.ok(Map.of("shifted", true));
    }

    @Operation(summary = "锁定后继步骤", description = "锁定指定节点的所有依赖后继节点(depends_on 关系的下游)")
    @PostMapping("/api/plans/{planId}/steps/lock-successors")
    public Result lockSuccessors(@PathVariable Long planId, @RequestBody Map<String, Object> body) {
        String nodeId = (String) body.get("node_id");
        List<Long> lockedIds = stepService.lockSuccessors(planId, nodeId);
        return Result.ok(Map.of("locked_ids", lockedIds));
    }

    @Operation(summary = "节点状态变更(原子)", description = "原子操作：锁定后继 + 插入复习步骤 + 更新计划进度计数")
    @PostMapping("/api/plans/node-status-change")
    @Transactional(rollbackFor = Exception.class)
    public Result onNodeStatusChange(@RequestBody Map<String, Object> body) {
        Long userId = Long.valueOf(body.get("user_id").toString());
        String nodeId = (String) body.get("node_id");
        String newStatus = (String) body.get("new_status");
        Long planId = body.get("plan_id") != null ? Long.valueOf(body.get("plan_id").toString()) : null;

        LearningPlan plan;
        if (planId != null) {
            plan = planService.getById(planId);
        } else {
            plan = planService.getActiveByUserId(userId);
        }
        if (plan == null) {
            return Result.fail(404, "没有进行中的学习计划");
        }

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

        List<Long> lockedStepIds = stepService.lockSuccessors(plan.getId(), nodeId);

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

    // ==================== 对接 Python AI 的计划接口 ====================

    /**
     * 查询计划状态（含软着陆触发检测）。
     * Java 从 DB 读取 plan + steps，传入 Python 做分析。
     */
    @Operation(summary = "查询计划状态", description = "含软着陆触发检测（continue/warmup/regression_check）")
    @GetMapping("/api/plans/{planId}/status")
    public Result getPlanStatus(@PathVariable Long planId, @RequestParam Long userId) {
        try {
            LearningPlan plan = planService.getById(planId);
            if (plan == null) {
                return Result.fail(404, "计划不存在");
            }
            List<PlanStep> steps = stepService.listByPlanId(planId);

            Map<String, Object> planData = planToMap(plan);
            List<Map<String, Object>> stepsData = stepsToMapList(steps);

            Map<String, Object> status = pythonClient.getPlanStatusById(planId, planData, stepsData);
            return Result.ok(status);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 获取今日学习任务 + 资源建议。
     */
    @Operation(summary = "今日任务", description = "返回今日应完成的步骤+资源建议")
    @GetMapping("/api/plans/{planId}/today")
    public Result getTodayTasks(@PathVariable Long planId, @RequestParam Long userId) {
        try {
            LearningPlan plan = planService.getById(planId);
            if (plan == null) {
                return Result.fail(404, "计划不存在");
            }
            List<PlanStep> steps = stepService.listByPlanId(planId);

            Map<String, Object> planData = planToMap(plan);
            List<Map<String, Object>> stepsData = stepsToMapList(steps);
            Map<String, Float> masteries = buildMasteryMap(userId, plan.getCourseId());

            Map<String, Object> result = pythonClient.getTodayTasks(planId, planData, stepsData,
                    null, masteries);
            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 更新步骤进度 + 计算掌握度变化。
     */
    @Operation(summary = "更新步骤进度", description = "更新步骤进度并计算掌握度变化")
    @PostMapping("/api/plans/{planId}/progress")
    public Result updateProgress(@PathVariable Long planId, @RequestBody ProgressUpdateRequest body) {
        try {
            Long userId = UserHolder.getUser().getId();
            LearningPlan plan = planService.getById(planId);
            if (plan == null) {
                return Result.fail(404, "计划不存在");
            }
            List<PlanStep> steps = stepService.listByPlanId(planId);

            Map<String, Object> planData = planToMap(plan);
            List<Map<String, Object>> stepsData = stepsToMapList(steps);
            Map<String, Float> masteries = buildMasteryMap(userId, plan.getCourseId());

            Map<String, Object> result = pythonClient.updatePlanProgress(planId, planData, stepsData,
                    body.getStep_id(), body.getStep_order() != null ? body.getStep_order() : 0,
                    body.getStatus(), body.getActivity_type(), body.getScore(),
                    body.getDuration_minutes(), masteries);

            // 自动记录学习活动
            recordPlanActivity(userId, planId, body.getStep_id(),
                    body.getActivity_type(), body.getDuration_minutes(), body.getScore());
            // Python 返回的掌握度更新写回 node_masteries 表
            syncMasteryUpdates(result, plan.getCourseId(), userId);

            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    private void recordPlanActivity(Long userId, Long planId, Long stepId,
                                     String activityType, Integer duration, Float score) {
        try {
            LearningActivity activity = new LearningActivity()
                    .setUserId(userId)
                    .setPlanId(planId)
                    .setStepId(stepId)
                    .setActivityType(activityType != null ? activityType : "study")
                    .setDurationMinutes(duration != null ? duration : 0)
                    .setScore(score);
            activityService.save(activity);
        } catch (Exception e) {
            log.error("记录计划活动失败: userId={}, planId={}", userId, planId, e);
        }
    }

    /**
     * 回归检测管线（两阶段）。
     * 阶段1（不传 answers）：出题检测遗忘 → 阶段2（传 answers）：判分 + 重排
     */
    @Operation(summary = "回归检测", description = "两阶段回归检测：阶段1出题，阶段2判分+重排")
    @PostMapping("/api/plans/{planId}/regression-check")
    public Result regressionCheck(@PathVariable Long planId, @RequestBody RegressionCheckRequest body) {
        try {
            Long userId = UserHolder.getUser().getId();
            LearningPlan plan = planService.getById(planId);
            if (plan == null) {
                return Result.fail(404, "计划不存在");
            }
            List<PlanStep> steps = stepService.listByPlanId(planId);

            Map<String, Object> planData = planToMap(plan);
            List<Map<String, Object>> stepsData = stepsToMapList(steps);
            int daysIdle = body.getDays_idle() != null ? body.getDays_idle() : 0;

            Map<String, Object> result = pythonClient.regressionCheck(planId, userId,
                    body.getAnswers(), planData, stepsData, daysIdle);
            // Python 返回的掌握度更新写回 node_masteries 表
            syncMasteryUpdates(result, plan.getCourseId(), userId);
            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 获取未来N天的复习日程（间隔重复提醒）。
     */
    @Operation(summary = "复习日程", description = "获取未来N天的间隔重复复习日程")
    @GetMapping("/api/plans/{planId}/review-schedule")
    public Result getReviewSchedule(@PathVariable Long planId,
                                     @RequestParam Long userId,
                                     @RequestParam(defaultValue = "7") int daysAhead) {
        try {
            LearningPlan plan = planService.getById(planId);
            if (plan == null) {
                return Result.fail(404, "计划不存在");
            }
            List<PlanStep> steps = stepService.listByPlanId(planId);
            List<Map<String, Object>> stepsData = stepsToMapList(steps);

            Map<String, Object> result = pythonClient.getReviewSchedule(planId, stepsData, daysAhead);
            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 完成学习步骤后触发巩固练习生成。
     */
    @Operation(summary = "步骤完成巩固", description = "完成一个学习步骤后生成巩固练习题")
    @PostMapping("/api/plans/{planId}/complete-step")
    public Result completeStep(@PathVariable Long planId, @RequestBody CompleteStepRequest body) {
        try {
            LearningPlan plan = planService.getById(planId);
            if (plan == null) {
                return Result.fail(404, "计划不存在");
            }
            List<PlanStep> steps = stepService.listByPlanId(planId);

            Map<String, Object> planData = planToMap(plan);
            List<Map<String, Object>> stepsData = stepsToMapList(steps);

            Map<String, Object> result = pythonClient.completePlanStep(planId, body.getStep(),
                    planData, stepsData);
            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 将 Python 返回的 mastery_updates 同步到 node_masteries 表。
     * Python 返回格式: {"mastery_updates": {"nodeId": {"new_mastery": 0.6}, ...}}
     */
    @SuppressWarnings("unchecked")
    private void syncMasteryUpdates(Map<String, Object> pythonResult, String courseId, Long userId) {
        try {
            Object updatesObj = pythonResult.get("data");
            if (!(updatesObj instanceof Map)) return;
            Map<String, Object> data = (Map<String, Object>) updatesObj;
            Object muObj = data.get("mastery_updates");
            if (!(muObj instanceof Map)) return;
            Map<String, Object> masteryUpdates = (Map<String, Object>) muObj;

            for (Map.Entry<String, Object> entry : masteryUpdates.entrySet()) {
                String nodeId = entry.getKey();
                if (!(entry.getValue() instanceof Map)) continue;
                Map<String, Object> update = (Map<String, Object>) entry.getValue();
                Object newMasteryObj = update.get("new_mastery");
                if (newMasteryObj == null) continue;
                float newMastery = ((Number) newMasteryObj).floatValue();
                // 查询现有记录获取 review_count
                NodeMastery existing = masteryService.getByUserIdAndNodeId(userId, nodeId);
                int reviewCount = existing != null ? existing.getReviewCount() + 1 : 1;
                masteryService.upsert(userId, nodeId, courseId, newMastery, reviewCount);
            }
        } catch (Exception e) {
            log.error("同步掌握度更新失败: userId={}, courseId={}", userId, courseId, e);
        }
    }

    // ==================== 辅助方法 ====================

    /** 将 LearningPlan 实体转为 Map，供 PythonClient 传参 */
    private Map<String, Object> planToMap(LearningPlan plan) {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("id", plan.getId());
        map.put("user_id", plan.getUserId());
        map.put("course_id", plan.getCourseId());
        map.put("title", plan.getTitle());
        map.put("status", plan.getStatus());
        map.put("total_steps", plan.getTotalSteps());
        map.put("completed_steps", plan.getCompletedSteps());
        return map;
    }

    /** 将 PlanStep 列表转为 Map 列表，供 PythonClient 传参 */
    private List<Map<String, Object>> stepsToMapList(List<PlanStep> steps) {
        return steps.stream().map(s -> {
            Map<String, Object> map = new LinkedHashMap<>();
            map.put("id", s.getId());
            map.put("plan_id", s.getPlanId());
            map.put("node_id", s.getNodeId());
            map.put("knowledge_node_id", s.getNodeId());
            map.put("topic", s.getTopic());
            map.put("step_order", s.getOrder());
            map.put("status", s.getStatus());
            map.put("estimated_days", s.getEstimatedDays());
            map.put("topic_difficulty", s.getTopicDifficulty());
            return map;
        }).collect(Collectors.toList());
    }

    /** 构建用户掌握度映射 */
    private Map<String, Float> buildMasteryMap(Long userId, String courseId) {
        return masteryService.buildMasteryMap(userId, courseId);
    }

    private int toInt(Object value, int defaultValue) {
        if (value instanceof Number) return ((Number) value).intValue();
        if (value instanceof String) return Integer.parseInt((String) value);
        return defaultValue;
    }
}
