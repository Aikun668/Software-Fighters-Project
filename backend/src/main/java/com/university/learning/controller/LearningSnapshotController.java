package com.university.learning.controller;

import com.university.learning.client.PythonClient;
import com.university.learning.common.Result;
import com.university.learning.entity.LearningPlan;
import com.university.learning.entity.NodeMastery;
import com.university.learning.entity.PlanStep;
import com.university.learning.entity.StudentProfile;
import com.university.learning.service.ILearningPlanService;
import com.university.learning.service.INodeMasteryService;
import com.university.learning.service.IPlanStepService;
import com.university.learning.service.IStudentProfileService;
import com.university.learning.utils.UserHolder;
import io.swagger.v3.oas.annotations.Operation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 只读学习快照桥接（P1 §二，P2 遗留指导 §四）。
 *
 * <p><b>职责边界</b>：本 Controller 只做「取事实 → 传上下文 → 转结果」三件事。
 * 学生身份只从登录态取得，不接受前端传入 {@code userId}；不重算下一步
 * （{@code next_action} 由 Python 计算并原样透传）；不改任何长期状态。</p>
 *
 * <p><b>零写入</b>：无 {@code @Transactional}，不调用任何 save/update；
 * 无论成功、无计划、无掌握度或无建议，都不会写 {@code node_masteries}、
 * 计划、学习记录或画像。</p>
 *
 * <p><b>响应形状</b>：沿用本项目既有约定，返回 Python 信封
 * {@code {success, data:{十键快照}}}，包在 {@code Result.data} 内。
 * 这样 Python 的 {@code freshness} / {@code next_action} 与错误语义
 * （如非试点课程的 {@code next_action: null}）都是零损耗透传。</p>
 */
@Slf4j
@RestController
@RequestMapping("/api/learning-snapshot")
@RequiredArgsConstructor
public class LearningSnapshotController {

    /** courseId 缺失时的既有试点约定默认课程（P2 遗留指导 §4.2） */
    private static final String DEFAULT_COURSE_ID = "ai_intro";

    private static final DateTimeFormatter ISO_DATE_TIME = DateTimeFormatter.ISO_LOCAL_DATE_TIME;

    private final ILearningPlanService planService;
    private final IPlanStepService stepService;
    private final INodeMasteryService masteryService;
    private final IStudentProfileService profileService;
    private final PythonClient pythonClient;

    /**
     * 组装只读学习快照。
     *
     * @param courseId 课程 ID；缺失时回落 {@link #DEFAULT_COURSE_ID} 并记 WARN 日志，
     *                 使回落行为在日志中可识别（P2 遗留指导 §4.2）
     */
    @Operation(summary = "获取学习快照",
            description = "读取登录用户的学习事实，调用 Python 组装只读 LearningSnapshot（含 freshness 与 next_action）。零写入。")
    @GetMapping
    public Result getSnapshot(@RequestParam(required = false) String courseId) {
        Long userId = UserHolder.getUser().getId();

        String effectiveCourseId = courseId;
        if (effectiveCourseId == null || effectiveCourseId.isBlank()) {
            effectiveCourseId = DEFAULT_COURSE_ID;
            log.warn("学习快照 courseId 缺失，回落默认试点课程: userId={}, courseId={}", userId, effectiveCourseId);
        }

        Map<String, Object> planData = Collections.emptyMap();
        List<Map<String, Object>> stepsData = Collections.emptyList();

        LearningPlan plan = planService.getActiveByUserId(userId);
        if (plan == null) {
            log.info("学习快照无进行中计划: userId={}, courseId={}", userId, effectiveCourseId);
        } else if (plan.getCourseId() != null && !plan.getCourseId().equals(effectiveCourseId)) {
            // 进行中的计划属于另一门课程：对本课程而言不存在活跃计划。
            // 若强行拼入，会把别课的计划/步骤伪装成本课事实，故如实降级为空。
            log.warn("学习快照命中他课计划，按无计划处理: userId={}, 请求课程={}, 计划课程={}, planId={}",
                    userId, effectiveCourseId, plan.getCourseId(), plan.getId());
        } else {
            planData = planToSnapshotMap(plan);
            stepsData = stepsToSnapshotMapList(stepService.listByPlanId(plan.getId()));
        }

        Map<String, Float> masteries = buildMasteryMap(userId, effectiveCourseId);
        Map<String, Object> studentProfile = buildProfileMap(userId);

        Map<String, Object> pythonResponse = pythonClient.getLearningSnapshot(
                userId, effectiveCourseId, planData, stepsData, masteries, studentProfile);

        log.info("学习快照已生成: userId={}, courseId={}, 计划={}, 步骤数={}, 掌握度节点数={}, 画像={}",
                userId, effectiveCourseId, planData.isEmpty() ? "无" : planData.get("id"),
                stepsData.size(), masteries.size(), studentProfile.isEmpty() ? "无" : "有");

        return Result.ok(pythonResponse);
    }

    /**
     * 计划元数据投影。
     *
     * <p>比 {@code LearningPlanController.planToMap} 多 {@code last_activity_at} ——
     * Python 的 {@code _days_idle} / {@code interrupted} 判定依赖它。</p>
     */
    private Map<String, Object> planToSnapshotMap(LearningPlan plan) {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("id", plan.getId());
        map.put("user_id", plan.getUserId());
        map.put("course_id", plan.getCourseId());
        map.put("title", plan.getTitle());
        map.put("status", plan.getStatus());
        map.put("total_steps", plan.getTotalSteps());
        map.put("completed_steps", plan.getCompletedSteps());
        map.put("last_activity_at", toIsoString(plan.getLastActivityAt()));
        return map;
    }

    /**
     * 计划步骤投影。
     *
     * <p>比 {@code LearningPlanController.stepsToMapList} 多 {@code last_review_at} /
     * {@code review_count} / {@code mastery_current} / {@code mastery_after} ——
     * Python 的 {@code _review_due_candidates} 与 {@code _step_mastery_snapshot} 依赖它们。</p>
     *
     * <p>{@code mastery_current} / {@code mastery_after} 仅作展示兜底：阅读模型
     * 只让它们在请求级 {@code masteries} 缺失时充当来源标识，不参与衰减计算
     * （P1 §3.3 / P2 Task 1.5）。</p>
     */
    private List<Map<String, Object>> stepsToSnapshotMapList(List<PlanStep> steps) {
        if (steps == null) {
            return Collections.emptyList();
        }
        List<Map<String, Object>> list = new ArrayList<>(steps.size());
        for (PlanStep s : steps) {
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
            map.put("mastery_current", s.getMasteryCurrent());
            map.put("mastery_after", s.getMasteryAfter());
            map.put("review_count", s.getReviewCount());
            map.put("last_review_at", toIsoString(s.getLastReviewAt()));
            list.add(map);
        }
        return list;
    }

    /** 从唯一掌握度真源构建 map（缺失掌握度节点在此不会被伪造）。 */
    private Map<String, Float> buildMasteryMap(Long userId, String courseId) {
        List<NodeMastery> list = masteryService.listByUserIdAndCourseId(userId, courseId);
        Map<String, Float> map = new HashMap<>();
        for (NodeMastery nm : list) {
            map.put(nm.getNodeId(), nm.getMastery() != null ? nm.getMastery() : 0f);
        }
        return map;
    }

    /** 复用现有 {@code rawProfileJson} 转 map 的处理方式（与 PathController 一致）。 */
    @SuppressWarnings("unchecked")
    private Map<String, Object> buildProfileMap(Long userId) {
        StudentProfile profile = profileService.getByUserId(userId);
        if (profile != null && profile.getRawProfileJson() instanceof Map) {
            return (Map<String, Object>) profile.getRawProfileJson();
        }
        return Collections.emptyMap();
    }

    /** LocalDateTime → ISO8601 字符串；null 保持 null（Python 侧视为不可解析）。 */
    private String toIsoString(LocalDateTime value) {
        return value == null ? null : ISO_DATE_TIME.format(value);
    }
}
