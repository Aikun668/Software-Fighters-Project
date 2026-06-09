package com.university.learning.controller;

import com.university.learning.common.Result;
import com.university.learning.entity.LearningActivity;
import com.university.learning.service.ILearningActivityService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 学习活动记录接口
 */
@RestController
@RequestMapping("/api/learning-activities")
@RequiredArgsConstructor
public class LearningActivityController {

    private final ILearningActivityService activityService;

    /** 创建一条学习活动记录 */
    @PostMapping
    public Result create(@RequestBody Map<String, Object> body) {
        Long userId = Long.valueOf(body.get("user_id").toString());
        LearningActivity activity = new LearningActivity()
                .setUserId(userId)
                .setPlanId(body.get("plan_id") != null ? Long.valueOf(body.get("plan_id").toString()) : null)
                .setStepId(body.get("step_id") != null ? Long.valueOf(body.get("step_id").toString()) : null)
                .setActivityType((String) body.get("activity_type"))
                .setDurationMinutes(body.get("duration_minutes") != null ? toInt(body.get("duration_minutes")) : 0)
                .setScore(body.get("score") != null ? Float.valueOf(body.get("score").toString()) : null);
        activityService.save(activity);
        return Result.ok(Map.of("id", activity.getId()));
    }

    /** 获取最近的学习活动记录列表 */
    @GetMapping
    public Result listRecent(@RequestParam Long userId,
                             @RequestParam(defaultValue = "20") int limit) {
        List<Map<String, Object>> list = activityService.listRecentWithTopic(userId, limit);
        return Result.ok(list);
    }

    /** 获取用户学习活动统计摘要 */
    @GetMapping("/stats")
    public Result getStats(@RequestParam Long userId) {
        Map<String, Object> stats = activityService.getStats(userId);
        return Result.ok(stats);
    }

    /** 获取用户得分趋势（按日期聚合） */
    @GetMapping("/score-trend")
    public Result getScoreTrend(@RequestParam Long userId,
                                @RequestParam(defaultValue = "30") int days) {
        List<Map<String, Object>> trend = activityService.getScoreTrend(userId, days);
        return Result.ok(trend);
    }

    /** 获取用户总练习次数 */
    @GetMapping("/count-exercises")
    public Result countExercises(@RequestParam Long userId) {
        Long count = activityService.countExercises(userId);
        return Result.ok(Map.of("count", count));
    }

    private int toInt(Object value) {
        if (value instanceof Number) return ((Number) value).intValue();
        return Integer.parseInt(value.toString());
    }
}
