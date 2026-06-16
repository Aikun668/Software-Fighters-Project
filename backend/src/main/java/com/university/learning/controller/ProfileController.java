package com.university.learning.controller;

import com.university.learning.client.PythonClient;
import com.university.learning.common.Result;
import com.university.learning.entity.Conversation;
import com.university.learning.entity.Message;
import com.university.learning.entity.StudentProfile;
import com.university.learning.service.IConversationService;
import com.university.learning.service.IMessageService;
import com.university.learning.service.IStudentProfileService;
import com.university.learning.utils.UserHolder;
import io.swagger.v3.oas.annotations.Operation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.*;
import java.util.stream.Collectors;

@Slf4j
@RestController
@RequestMapping("/api/profile")
@RequiredArgsConstructor
public class ProfileController {

    private final PythonClient pythonClient;
    private final IStudentProfileService profileService;
    private final IConversationService conversationService;
    private final IMessageService messageService;

    @Operation(summary = "画像构建对话", description = "通过 AI 引导式对话构建学生学习画像(SSE 流式)，对话结束自动保存画像")
    @PostMapping("/chat")
    public SseEmitter chatBuildProfile(@RequestBody Map<String, Object> request) {
        Long userId = getUserId();

        @SuppressWarnings("unchecked")
        List<Map<String, String>> messages = (List<Map<String, String>>) request.get("messages");

        Conversation conversation = getOrCreateProfileConversation(userId);
        final Long convId = conversation.getId();

        if (messages != null) {
            for (Map<String, String> msg : messages) {
                if ("user".equals(msg.get("role"))) {
                    messageService.save(new Message()
                            .setConversationId(convId)
                            .setRole("user")
                            .setContent(msg.get("content"))
                            .setMode("profile"));
                }
            }
        }

        List<Map<String, Object>> history = loadHistory(convId, 50);

        return pythonClient.buildProfileStream(userId, messages, (profileData) -> {
            saveProfileToDb(userId, profileData);
            saveAiResponse(convId, profileData);
            updateConversationTitle(convId);
        });
    }

    @Operation(summary = "查询画像完整度")
    @GetMapping("/status")
    public Result getProfileStatus() {
        try {
            Long userId = getUserId();
            // 获取学生画像快照，传给 Python 做完整度检测
            StudentProfile profile = profileService.getByUserId(userId);
            @SuppressWarnings("unchecked")
            Map<String, Object> profileMap = profile != null && profile.getRawProfileJson() instanceof Map
                    ? (Map<String, Object>) profile.getRawProfileJson()
                    : null;
            Map<String, Object> status = pythonClient.getProfileStatus(userId, profileMap);
            return Result.ok(status);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    @Operation(summary = "获取学生画像")
    @GetMapping("/{userId}")
    public Result getProfile(@PathVariable Long userId) {
        StudentProfile profile = profileService.getByUserId(userId);
        if (profile == null) {
            return Result.fail(404, "画像不存在");
        }
        return Result.ok(profile);
    }

    private Conversation getOrCreateProfileConversation(Long userId) {
        List<Conversation> list = conversationService.listByUserId(userId);
        for (Conversation conv : list) {
            if ("active".equals(conv.getStatus()) && "画像构建".equals(conv.getTitle())) {
                return conv;
            }
        }
        Conversation conv = new Conversation()
                .setUserId(userId)
                .setTitle("画像构建")
                .setStatus("active");
        conversationService.save(conv);
        return conv;
    }

    private List<Map<String, Object>> loadHistory(Long conversationId, int limit) {
        List<Message> messages = messageService.listByConversationId(conversationId);
        if (messages.size() > limit) {
            messages = messages.subList(messages.size() - limit, messages.size());
        }
        return messages.stream().map(m -> {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("role", m.getRole());
            item.put("content", m.getContent());
            return item;
        }).collect(Collectors.toList());
    }

    private void saveAiResponse(Long conversationId, Map<String, Object> doneData) {
        try {
            String response = (String) doneData.get("_response_text");
            if (response == null || response.isEmpty()) {
                response = (String) doneData.getOrDefault("response", "");
            }
            if (response == null || response.isEmpty()) {
                response = "画像构建完成";
            }

            messageService.save(new Message()
                    .setConversationId(conversationId)
                    .setRole("assistant")
                    .setContent(response)
                    .setMode("profile"));
        } catch (Exception e) {
            log.error("保存画像对话AI回复失败", e);
        }
    }

    private void updateConversationTitle(Long conversationId) {
        try {
            Conversation conv = conversationService.getById(conversationId);
            if (conv != null && "画像构建".equals(conv.getTitle())) {
                StudentProfile profile = profileService.getByUserId(conv.getUserId());
                if (profile != null && profile.getKnowledgeBase() != null && profile.getKnowledgeBase() > 0) {
                    conv.setTitle("画像构建完成");
                    conv.setStatus("archived");
                    conv.setSummary("学生画像已构建完成，包含知识基础、认知风格、学习目标等维度");
                    conversationService.updateById(conv);
                }
            }
        } catch (Exception e) {
            log.error("更新会话标题失败", e);
        }
    }

    private void saveProfileToDb(Long userId, Map<String, Object> data) {
        try {
            StudentProfile profile = new StudentProfile();
            profile.setUserId(userId);

            // 只设非 null 值，避免把 DB 中已有的有效值覆盖为 null
            if (data.get("knowledge_base") != null) {
                profile.setKnowledgeBase(toInteger(data.get("knowledge_base")));
            }
            if (data.get("cognitive_style") != null) {
                profile.setCognitiveStyle((String) data.get("cognitive_style"));
            }
            if (data.get("learning_goal") != null) {
                profile.setLearningGoal((String) data.get("learning_goal"));
            }
            if (data.get("weak_points") != null) {
                profile.setWeakPoints(data.get("weak_points"));
            }
            if (data.get("learning_pace") != null) {
                profile.setLearningPace((String) data.get("learning_pace"));
            }
            if (data.get("interest_direction") != null) {
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
