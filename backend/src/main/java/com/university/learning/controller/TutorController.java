package com.university.learning.controller;

import com.university.learning.client.PythonClient;
import com.university.learning.entity.StudentProfile;
import com.university.learning.service.IStudentProfileService;
import com.university.learning.utils.UserHolder;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.HashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/tutor")
@RequiredArgsConstructor
public class TutorController {

    private final PythonClient pythonClient;
    private final IStudentProfileService profileService;

    /**
     * 智能答疑
     * 入参: {content: "什么是机器学习？", conversation_id: "xxx"}
     */
    @PostMapping("/chat")
    public SseEmitter tutorChat(@RequestBody Map<String, Object> request) {
        Long userId = getUserId();
        String content = (String) request.get("content");
        String conversationId = (String) request.get("conversation_id");
        Map<String, Object> profileMap = buildProfileMap(userId);

        return pythonClient.tutorChatStream(userId, content, conversationId, profileMap);
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

    private Long getUserId() {

        return UserHolder.getUser().getId();
    }
}