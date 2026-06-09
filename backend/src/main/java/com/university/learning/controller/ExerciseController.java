package com.university.learning.controller;

import com.university.learning.client.PythonClient;
import com.university.learning.common.Result;
import com.university.learning.entity.LearningRecord;
import com.university.learning.entity.Resource;
import com.university.learning.entity.StudentProfile;
import com.university.learning.service.ILearningRecordService;
import com.university.learning.service.IResourceService;
import com.university.learning.service.IStudentProfileService;
import com.university.learning.utils.UserHolder;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/exercise")
@RequiredArgsConstructor
public class ExerciseController {


    private final PythonClient pythonClient;
    private final IStudentProfileService profileService;
    private final IResourceService resourceService;
    private final ILearningRecordService learningRecordService;


    /**
     * 生成练习题
     */
    @PostMapping("/generate")
    public SseEmitter generateExercises(@RequestBody Map<String, Object> request) {
        Long userId = getUserId();
        String topic = (String) request.get("topic");
        Integer count = request.get("count") != null ? (Integer) request.get("count") : 5;
        String difficulty = (String) request.getOrDefault("difficulty", "medium");
        Map<String, Object> profileMap = buildProfileMap(userId);

        return pythonClient.generateExercisesStream(userId, topic, count, difficulty, profileMap, (doneData) -> {
            saveExercisesToDb(userId, topic, difficulty, doneData);
        });
    }

    /**
     * 保存练习题到resources表
     */
    private void saveExercisesToDb(Long userId, String topic, String difficulty, Map<String, Object> doneData) {
        try {
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> questions = (List<Map<String, Object>>) doneData.get("questions");
            if (questions == null || questions.isEmpty()) return;

            Resource resource = new Resource();
            resource.setUserId(userId);
            resource.setType("exercise");
            resource.setTopic(topic);

            // 把题目和难度一起存
            Map<String, Object> contentJson = new HashMap<>();
            contentJson.put("questions", questions);
            contentJson.put("count", questions.size());
            contentJson.put("difficulty", difficulty);
            resource.setContentJson(contentJson);

            resourceService.save(resource);
            log.info("练习题已保存: userId={}, topic={}, count={}", userId, topic, questions.size());
        } catch (Exception e) {
            log.error("保存练习题失败: userId={}, topic={}", userId, topic, e);
        }
    }

    /**
     * 批改练习题
     * 入参: {type: "choice", user_answer: "B", correct_answer: "B", choices: [...], multi: false, points: 5}
     */
    @PostMapping("/grade")
    public Result gradeExercise(@RequestBody Map<String, Object> request) {
        try {
            Long userId = getUserId();
            String type = (String) request.get("type");
            String userAnswer = (String) request.get("user_answer");
            Long resourceId = request.get("resource_id") != null ?
                    Long.valueOf(request.get("resource_id").toString()) : null;

            Map<String, Object> result;
            if ("choice".equals(type)) {
                String correctAnswer = (String) request.get("correct_answer");
                @SuppressWarnings("unchecked")
                List<String> choices = (List<String>) request.get("choices");
                Boolean multi = request.get("multi") != null ? (Boolean) request.get("multi") : false;
                Integer points = request.get("points") != null ? (Integer) request.get("points") : 1;
                result = pythonClient.gradeExercise(type, userAnswer, correctAnswer, choices, multi, points, null, null);
            } else {
                String referenceAnswer = (String) request.get("reference_answer");
                String rubric = (String) request.get("rubric");
                result = pythonClient.gradeExercise(type, userAnswer, null, null, null, null, referenceAnswer, rubric);
            }

            // ⭐ 批改后存学习记录
            if (resourceId != null && result != null) {
                saveLearningRecord(userId, resourceId, result, request);
            }

            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 生成评估报告
     */
    @PostMapping("/report")
    public Result getReport(@RequestBody Map<String, Object> request) {
        try {
            Long userId = getUserId();

            @SuppressWarnings("unchecked")
            Map<String, Object> evaluationResults = (Map<String, Object>) request.get("evaluation_results");

            Map<String, Object> report = pythonClient.getEvaluationReport(userId, evaluationResults);
            return Result.ok(report);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

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

    private void saveLearningRecord(Long userId, Long resourceId,
                                    Map<String, Object> gradeResult,
                                    Map<String, Object> request) {
        try {
            Map<String, Object> data = (Map<String, Object>) gradeResult.get("data");
            if (data == null) return;

            boolean correct = (boolean) data.getOrDefault("correct", false);
            int points = request.get("points") != null ? (int) request.get("points") : 1;
            int score = correct ? points : 0;

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
    private Long getUserId() {

        return UserHolder.getUser().getId();
    }
}