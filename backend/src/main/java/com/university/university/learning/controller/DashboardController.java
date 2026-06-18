package com.university.university.learning.controller;

import com.university.learning.common.Result;
import com.university.learning.entity.LearningPlan;
import com.university.learning.entity.PlanStep;
import com.university.learning.service.ILearningActivityService;
import com.university.learning.service.ILearningPlanService;
import com.university.learning.service.IPlanStepService;
import com.university.learning.utils.UserHolder;
import com.university.learning.vo.DashboardVO;
import io.swagger.v3.oas.annotations.Operation;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.List;

/**
 * 仪表盘控制器，聚合展示首页核心数据。
 */
@RestController
@RequestMapping("/api/dashboard")
@RequiredArgsConstructor
public class DashboardController {

    private final ILearningActivityService activityService;
    private final ILearningPlanService planService;
    private final IPlanStepService stepService;

    /**
     * 返回首页仪表盘数据：连续学习天数、总学习时长、各计划进度。
     */
    @Operation(summary = "仪表盘数据", description = "返回连续学习天数、总学习时长、各计划进度")
    @GetMapping
    public Result getDashboard() {
        Long userId = UserHolder.getUser().getId();

        DashboardVO vo = new DashboardVO();
        // 连续学习天数
        vo.setConsecutiveDays(activityService.getConsecutiveDays(userId));
        // 总学习时长
        vo.setTotalMinutes(activityService.getTotalMinutes(userId));
        // 总做题次数
        vo.setTotalExercises(activityService.countExercises(userId));

        // 各计划进度
        List<LearningPlan> plans = planService.listByUserId(userId);
        List<DashboardVO.PlanProgress> planList = new ArrayList<>();
        for (LearningPlan plan : plans) {
            List<PlanStep> steps = stepService.listByPlanId(plan.getId());
            int completed = 0;
            for (PlanStep s : steps) {
                if ("completed".equals(s.getStatus())) completed++;
            }
            int total = Math.max(steps.size(), plan.getTotalSteps());
            int pct = total > 0 ? completed * 100 / total : 0;

            planList.add(new DashboardVO.PlanProgress()
                    .setPlanId(plan.getId())
                    .setTitle(plan.getTitle())
                    .setStatus(plan.getStatus())
                    .setCompletedSteps(completed)
                    .setTotalSteps(total)
                    .setProgressPct(pct));
        }
        vo.setPlans(planList);

        return Result.ok(vo);
    }
}
