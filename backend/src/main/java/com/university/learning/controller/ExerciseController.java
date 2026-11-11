package com.university.learning.controller;

import com.university.learning.client.PythonClient;
import com.university.learning.common.Result;
import com.university.learning.dto.*;
import com.university.learning.entity.LearningRecord;
import com.university.learning.entity.NodeMastery;
import com.university.learning.entity.Resource;
import com.university.learning.entity.StudentProfile;
import com.university.learning.service.ILearningRecordService;
import com.university.learning.service.INodeMasteryService;
import com.university.learning.service.IResourceService;
import com.university.learning.service.IStudentProfileService;
import com.university.learning.utils.UserHolder;
import io.swagger.v3.oas.annotations.Operation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 练习题控制器，处理练习题的生成、批改和评估报告。
 */
@Slf4j
@RestController
@RequestMapping("/api/exercise")
@RequiredArgsConstructor
public class ExerciseController {

    private final PythonClient pythonClient;
    private final IStudentProfileService profileService;
    private final IResourceService resourceService;
    private final ILearningRecordService learningRecordService;
    private final INodeMasteryService masteryService;

    /**
     * 生成练习题（SSE 流式），完成后自动入库。
     *
     * @param request 包含 topic（可选）、count（默认5）、difficulty（默认medium）
     * @return SSE 流式响应
     */
    @Operation(summary = "生成练习题", description = "根据 topic 或 knowledge_node_id 生成练习题(SSE 流式)，完成后自动入库。strategy: weakness/review/new")
    @PostMapping("/generate")
    public SseEmitter generateExercises(@RequestBody ExerciseGenRequest request) {
        Long userId = getUserId();
        String topic = request.getTopic();
        String knowledgeNodeId = request.getKnowledge_node_id();
        String strategy = request.getStrategy();
        int count = request.getCount() != null ? request.getCount() : 5;
        String difficulty = request.getDifficulty() != null ? request.getDifficulty() : "medium";
        Map<String, Object> profileMap = buildProfileMap(userId);

        return pythonClient.generateExercisesStream(userId, topic, knowledgeNodeId, strategy,
                count, difficulty, profileMap, (doneData) -> {
            if (Boolean.TRUE.equals(doneData.get("_stream_error"))) {
                return;
            }
            saveExercisesToDb(userId, topic, difficulty, doneData);
        });
    }

    /**
     * 批改练习题，支持选择/填空/代码/论述等多种题型。
     * 客观题传 correct_answer，主观题传 reference_answer 和 rubric。
     *
     * @param request 批改请求参数
     * @return 批改结果
     */
    @Operation(summary = "批改练习题", description = "支持 choice/short_answer/code 题型，客观题传 correct_answer，主观题传 reference_answer")
    @PostMapping("/grade")
    public Result gradeExercise(@RequestBody GradeRequest request) {
        try {
            Long userId = getUserId();
            String type = request.getType();
            String userAnswer = request.getUser_answer();
            Long resourceId = request.getResource_id();

            Map<String, Object> result;
            if ("choice".equals(type)) {
                result = pythonClient.gradeExercise(type, userAnswer, request.getCorrect_answer(),
                        request.getChoices(), request.getMulti() != null ? request.getMulti() : false,
                        request.getPoints() != null ? request.getPoints() : 1, null, null);
            } else {
                result = pythonClient.gradeExercise(type, userAnswer, null, null, null, null,
                        request.getReference_answer(), request.getRubric());
            }

            if (resourceId != null && result != null) {
                saveLearningRecord(userId, resourceId, result, request.getPoints());
            }

            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 根据答题评估结果，调用 AI 生成学习评估报告。
     *
     * @param request 包含 evaluation_results 字段
     * @return 评估报告
     */
    @Operation(summary = "生成评估报告", description = "根据答题评估结果生成学习评估报告")
    @PostMapping("/report")
    public Result getReport(@RequestBody EvaluationReportRequest request) {
        try {
            Long userId = getUserId();
            Map<String, Object> report = pythonClient.getEvaluationReport(userId, request.getEvaluation_results());
            return Result.ok(report);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 错题深度分析，解释错误原因和改进方法。
     */
    @Operation(summary = "错题分析", description = "对错题进行深度分析，解释错误原因和改进方法")
    @PostMapping("/error-analysis")
    public Result errorAnalysis(@RequestBody ErrorAnalysisRequest request) {
        try {
            Map<String, Object> result = pythonClient.errorAnalysis(request.getErrors(), request.getLevel());
            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 将练习题匹配到知识图谱节点。
     */
    @Operation(summary = "练习题分类", description = "将练习题匹配到知识图谱节点")
    @PostMapping("/categorize")
    public Result categorizeExercises(@RequestBody CategorizeExerciseRequest request) {
        try {
            String courseId = request.getCourse_id() != null ? request.getCourse_id() : "ai_intro";
            Map<String, Object> result = pythonClient.categorizeExercises(
                    request.getExercises(), request.getKnowledge_nodes(), courseId);
            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 分析一次练习会话，返回逐知识点报告 + 掌握度更新建议。
     */
    @Operation(summary = "会话分析", description = "分析一次练习会话，返回逐知识点报告+掌握度更新建议")
    @PostMapping("/session/analyze")
    public Result analyzeSession(@RequestBody SessionAnalyzeRequest request) {
        try {
            String courseId = request.getCourse_id() != null ? request.getCourse_id() : "ai_intro";
            Long userId = getUserId();
            Map<String, Float> masteries = buildMasteryMap(userId, courseId);
            Map<String, Object> result = pythonClient.analyzeSession(
                    request.getRecords(), masteries, courseId);
            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 练习仪表盘：练习统计 + 薄弱/强项 + 推荐节点。
     */
    @Operation(summary = "练习仪表盘", description = "练习统计+薄弱/强项+推荐节点")
    @PostMapping("/dashboard")
    public Result exerciseDashboard(@RequestBody ExerciseDashboardRequest request) {
        try {
            Long userId = getUserId();
            String courseId = request.getCourse_id() != null ? request.getCourse_id() : "ai_intro";
            Map<String, Float> masteries = buildMasteryMap(userId, courseId);
            Map<String, Object> result = pythonClient.getExerciseDashboard(
                    userId, masteries, request.getRecent_records(), courseId);
            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 练习数据反哺学生画像。
     */
    @Operation(summary = "画像增强", description = "练习数据反哺学生画像：合并薄弱点、强项、技能等级")
    @PostMapping("/profile/enrich")
    public Result enrichProfile(@RequestBody ProfileEnrichRequest request) {
        try {
            Long userId = getUserId();
            Map<String, Object> profileMap = buildProfileMap(userId);
            Map<String, Object> result = pythonClient.enrichProfileByExercise(
                    userId, profileMap, request.getRecent_records(),
                    request.getSession_analysis());
            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /** 构建用户掌握度映射 */
    private Map<String, Float> buildMasteryMap(Long userId, String courseId) {
        List<NodeMastery> list = masteryService.listByUserIdAndCourseId(userId, courseId);
        Map<String, Float> map = new HashMap<>();
        for (NodeMastery nm : list) {
            map.put(nm.getNodeId(), nm.getMastery() != null ? nm.getMastery() : 0f);
        }
        return map;
    }

    private Long getUserId(Map<String, Object> body) {
        if (body.containsKey("user_id")) {
            return Long.valueOf(body.get("user_id").toString());
        }
        return getUserId();
    }

    /**
     * 根据用户 ID 查询学生画像，构建传给 AI 模型的 profile 数据。
     */
    private Map<String, Object> buildProfileMap(Long userId) {
        StudentProfile profile = profileService.getByUserId(userId);
        if (profile == null) return new HashMap<>();

        Map<String, Object> map = new HashMap<>();
        map.put("knowledge_base", profile.getKnowledgeBase());
        map.put("cognitive_style", profile.getCognitiveStyle());
        map.put("learning_goal", profile.getLearningGoal());
        map.put("weak_points", profile.getWeakPoints());
        map.put("learning_pace", profile.getLearningPace());
        map.put("interest_direction", profile.getInterestDirection());
        return map;
    }

    /**
     * 保存或更新答题学习记录，根据批改结果计算得分和进度。
     */
    private void saveLearningRecord(Long userId, Long resourceId,
                                    Map<String, Object> gradeResult,
                                    Integer points) {
        try {
            Map<String, Object> data = (Map<String, Object>) gradeResult.get("data");
            if (data == null) return;

            boolean correct = (boolean) data.getOrDefault("correct", false);
            int pts = points != null ? points : 1;
            int score = correct ? pts : 0;

            // 查找已有记录，存在则更新，否则新建
            LearningRecord record = learningRecordService.getByUserAndResource(userId, resourceId);
            if (record == null) {
                record = new LearningRecord();
                record.setUserId(userId);
                record.setResourceId(resourceId);
            }

            record.setScore((float) score);
            record.setProgress(correct ? 100f : 0f);
            learningRecordService.saveOrUpdateProgress(record);

        } catch (Exception e) {
            log.error("保存答题记录失败", e);
        }
    }

    /**
     * 从当前登录用户上下文中获取用户 ID。
     */
    private Long getUserId() {
        return UserHolder.getUser().getId();
    }

    /**
     * 将生成的练习题保存到资源库。
     * topic 优先取请求参数，为 null 时从模型返回数据中提取，最后回退为"未知主题"。
     */
    private void saveExercisesToDb(Long userId, String topic, String difficulty, Map<String, Object> doneData) {
        try {
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> questions = (List<Map<String, Object>>) doneData.get("questions");
            if (questions == null || questions.isEmpty()) return;

            // 确定主题：请求参数 > 模型返回 > 默认值（显式判空，getOrDefault 不防 null 值）
            String resolvedTopic = topic;
            if (resolvedTopic == null) {
                resolvedTopic = (String) doneData.get("topic");
            }
            if (resolvedTopic == null) {
                resolvedTopic = "未知主题";
            }

            Resource resource = new Resource();
            resource.setUserId(userId);
            resource.setType("exercise");
            resource.setTopic(resolvedTopic);
            resource.setTitle(resolvedTopic + " 练习题");

            Map<String, Object> contentJson = new HashMap<>();
            contentJson.put("questions", questions);
            contentJson.put("count", questions.size());
            contentJson.put("difficulty", difficulty);
            resource.setContentJson(contentJson);

            resourceService.save(resource);
            log.info("练习题已保存: userId={}, topic={}, count={}", userId, resolvedTopic, questions.size());
        } catch (Exception e) {
            log.error("保存练习题失败: userId={}, topic={}", userId, topic, e);
        }
    }
}