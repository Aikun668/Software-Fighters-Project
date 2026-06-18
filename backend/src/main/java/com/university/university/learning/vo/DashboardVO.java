package com.university.university.learning.vo;

import lombok.Data;
import lombok.experimental.Accessors;

import java.util.List;

/**
 * 仪表盘数据 VO
 */
@Data
@Accessors(chain = true)
public class DashboardVO {
    /** 连续学习天数 */
    private int consecutiveDays;
    /** 总学习时长（分钟） */
    private int totalMinutes;
    /** 总做题次数 */
    private long totalExercises;
    /** 各计划进度 */
    private List<PlanProgress> plans;

    @Data
    @Accessors(chain = true)
    public static class PlanProgress {
        private Long planId;
        private String title;
        private String status;
        private int completedSteps;
        private int totalSteps;
        private int progressPct;
    }
}
