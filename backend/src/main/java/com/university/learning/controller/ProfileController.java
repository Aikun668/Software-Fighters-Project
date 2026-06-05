package com.university.learning.controller;

import com.university.learning.client.PythonClient;
import com.university.learning.common.Result;
import com.university.learning.entity.StudentProfile;
import com.university.learning.service.IStudentProfileService;
import com.university.learning.utils.UserHolder;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;
import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/profile")
@RequiredArgsConstructor
public class ProfileController {

    private final PythonClient pythonClient;
    private final IStudentProfileService profileService;

    /**
     * 画像构建对话（SSE流式 + 自动存库）
     */
    @PostMapping("/chat")
    public SseEmitter chatBuildProfile(@RequestBody Map<String, Object> request) {
        Long userId = getUserId();

        @SuppressWarnings("unchecked")
        List<Map<String, String>> messages = (List<Map<String, String>>) request.get("messages");

        return pythonClient.buildProfileStream(userId, messages, (profileData) -> {
            saveProfileToDb(userId, profileData);
        });
    }

    /**
     * 画像完整度查询
     */
    @GetMapping("/status")
    public Result getProfileStatus() {
        try {
            Long userId = getUserId();
            Map<String, Object> status = pythonClient.getProfileStatus(userId);
            return Result.ok(status);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 获取学生画像
     */
    @GetMapping("/{userId}")
    public Result getProfile(@PathVariable Long userId) {
        StudentProfile profile = profileService.getByUserId(userId);
        if (profile == null) {
            return Result.fail("画像不存在");
        }
        return Result.ok(profile);
    }

    /**
     * 保存画像到数据库（回调方法）
     */
    private void saveProfileToDb(Long userId, Map<String, Object> data) {
        try {
            StudentProfile profile = new StudentProfile();
            profile.setUserId(userId);

            if (data.containsKey("knowledge_base")) {
                profile.setKnowledgeBase(toInteger(data.get("knowledge_base")));
            }
            if (data.containsKey("cognitive_style")) {
                profile.setCognitiveStyle((String) data.get("cognitive_style"));
            }
            if (data.containsKey("learning_goal")) {
                profile.setLearningGoal((String) data.get("learning_goal"));
            }
            if (data.containsKey("weak_points")) {
                profile.setWeakPoints(data.get("weak_points"));
            }
            if (data.containsKey("learning_pace")) {
                profile.setLearningPace((String) data.get("learning_pace"));
            }
            if (data.containsKey("interest_direction")) {
                profile.setInterestDirection(data.get("interest_direction"));
            }

            profile.setRawProfileJson(data);
            profileService.saveOrUpdateProfile(userId, profile);
            log.info("画像已保存: userId={}", userId);

        } catch (Exception e) {
            log.error("保存画像失败: userId={}", userId, e);
        }
    }

    private Integer toInteger(Object value) {
        if (value instanceof Integer) return (Integer) value;
        if (value instanceof Number) return ((Number) value).intValue();
        return null;
    }

    private Long getUserId() {

        return UserHolder.getUser().getId();
    }
}