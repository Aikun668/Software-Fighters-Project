package com.university.university.learning.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.university.learning.entity.LearningActivity;
import com.university.learning.mapper.LearningActivityMapper;
import com.university.learning.service.ILearningActivityService;
import org.springframework.stereotype.Service;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;

/**
 * 学习活动记录服务实现
 */
@Service
public class LearningActivityServiceImpl extends ServiceImpl<LearningActivityMapper, LearningActivity> implements ILearningActivityService {

    @Override
    public List<Map<String, Object>> listRecentWithTopic(Long userId, int limit) {
        List<LearningActivity> list = this.list(
                new LambdaQueryWrapper<LearningActivity>()
                        .eq(LearningActivity::getUserId, userId)
                        .orderByDesc(LearningActivity::getCreatedAt)
                        .last("LIMIT " + limit)
        );

        List<Map<String, Object>> result = new ArrayList<>();
        for (LearningActivity a : list) {
            Map<String, Object> map = new LinkedHashMap<>();
            map.put("id", a.getId());
            map.put("user_id", a.getUserId());
            map.put("plan_id", a.getPlanId());
            map.put("step_id", a.getStepId());
            map.put("activity_type", a.getActivityType());
            map.put("duration_minutes", a.getDurationMinutes());
            map.put("score", a.getScore());
            map.put("created_at", a.getCreatedAt());
            result.add(map);
        }
        return result;
    }

    @Override
    public Map<String, Object> getStats(Long userId) {
        List<LearningActivity> all = this.list(
                new LambdaQueryWrapper<LearningActivity>()
                        .eq(LearningActivity::getUserId, userId)
        );

        int totalSessions = all.size();
        int totalMinutes = all.stream()
                .mapToInt(a -> a.getDurationMinutes() != null ? a.getDurationMinutes() : 0)
                .sum();

        // 计算首次和最近活动日期
        LocalDate firstDate = all.stream()
                .map(a -> a.getCreatedAt().toLocalDate())
                .min(LocalDate::compareTo)
                .orElse(null);
        LocalDate lastDate = all.stream()
                .map(a -> a.getCreatedAt().toLocalDate())
                .max(LocalDate::compareTo)
                .orElse(null);

        Map<String, Object> stats = new LinkedHashMap<>();
        stats.put("total_sessions", totalSessions);
        stats.put("total_minutes", totalMinutes);
        stats.put("first_date", firstDate != null ? firstDate.toString() : null);
        stats.put("last_date", lastDate != null ? lastDate.toString() : null);
        return stats;
    }

    @Override
    public List<Map<String, Object>> getScoreTrend(Long userId, int days) {
        LocalDateTime since = LocalDateTime.now().minusDays(days);
        List<LearningActivity> list = this.list(
                new LambdaQueryWrapper<LearningActivity>()
                        .eq(LearningActivity::getUserId, userId)
                        .ge(LearningActivity::getCreatedAt, since)
                        .orderByAsc(LearningActivity::getCreatedAt)
        );

        // 按日期分组聚合平均分
        Map<String, List<Float>> byDate = new LinkedHashMap<>();
        DateTimeFormatter fmt = DateTimeFormatter.ofPattern("yyyy-MM-dd");
        for (LearningActivity a : list) {
            String date = a.getCreatedAt().format(fmt);
            byDate.computeIfAbsent(date, k -> new ArrayList<>())
                    .add(a.getScore() != null ? a.getScore() : 0f);
        }

        List<Map<String, Object>> trend = new ArrayList<>();
        for (Map.Entry<String, List<Float>> entry : byDate.entrySet()) {
            double avg = entry.getValue().stream().mapToDouble(Float::doubleValue).average().orElse(0);
            Map<String, Object> point = new LinkedHashMap<>();
            point.put("date", entry.getKey());
            point.put("avg_score", Math.round(avg * 100.0) / 100.0);
            point.put("count", entry.getValue().size());
            trend.add(point);
        }
        return trend;
    }

    @Override
    public Long countExercises(Long userId) {
        return this.count(
                new LambdaQueryWrapper<LearningActivity>()
                        .eq(LearningActivity::getUserId, userId)
                        .eq(LearningActivity::getActivityType, "exercise")
        );
    }

    @Override
    public int getConsecutiveDays(Long userId) {
        // 查询用户有活动的所有日期，倒序排列
        List<LearningActivity> list = this.list(
                new LambdaQueryWrapper<LearningActivity>()
                        .eq(LearningActivity::getUserId, userId)
                        .orderByDesc(LearningActivity::getCreatedAt)
        );
        if (list.isEmpty()) return 0;

        // 从今天开始往前数连续天数
        Set<LocalDate> activeDays = new HashSet<>();
        for (LearningActivity a : list) {
            activeDays.add(a.getCreatedAt().toLocalDate());
        }

        int consecutive = 0;
        LocalDate today = LocalDate.now();
        // 检查今天或昨天是否有活动
        if (!activeDays.contains(today) && !activeDays.contains(today.minusDays(1))) {
            return 0; // 今天和昨天都没活动，连续中断
        }
        // 从今天/昨天开始倒推
        LocalDate check = activeDays.contains(today) ? today : today.minusDays(1);
        while (activeDays.contains(check)) {
            consecutive++;
            check = check.minusDays(1);
        }
        return consecutive;
    }

    @Override
    public int getTotalMinutes(Long userId) {
        List<LearningActivity> list = this.list(
                new LambdaQueryWrapper<LearningActivity>()
                        .eq(LearningActivity::getUserId, userId)
        );
        return list.stream()
                .mapToInt(a -> a.getDurationMinutes() != null ? a.getDurationMinutes() : 0)
                .sum();
    }
}
