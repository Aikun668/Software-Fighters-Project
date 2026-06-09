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
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.*;
import java.util.stream.Collectors;

/**
 * 学生画像接口 — 集成会话存储
 */
@Slf4j
@RestController
@RequestMapping("/api/profile")
@RequiredArgsConstructor
public class ProfileController {

    private final PythonClient pythonClient;
    private final IStudentProfileService profileService;
    private final IConversationService conversationService;
    private final IMessageService messageService;

    /**
     * 画像构建对话（SSE流式 + 自动存库）
     * 请求体: { "messages": [{"role":"user","content":"..."}], "conversation_id": 1 }
     */
    @PostMapping("/chat")
    public SseEmitter chatBuildProfile(@RequestBody Map<String, Object> request) {
        Long userId = getUserId();

        @SuppressWarnings("unchecked")
        List<Map<String, String>> messages = (List<Map<String, String>>) request.get("messages");

        // 获取或创建画像专用会话
        Conversation conversation = getOrCreateProfileConversation(userId);
        final Long convId = conversation.getId();

        // 保存用户消息
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

        // 加载历史上下文
        List<Map<String, Object>> history = loadHistory(convId, 50);

        // 调用AI + 回调保存画像和回复
        return pythonClient.buildProfileStream(userId, messages, (profileData) -> {
            saveProfileToDb(userId, profileData);
            saveAiResponse(convId, profileData);
            updateConversationTitle(convId);
        });
    }

    /** 画像完整度查询 */
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

    /** 获取学生画像 */
    @GetMapping("/{userId}")
    public Result getProfile(@PathVariable Long userId) {
        StudentProfile profile = profileService.getByUserId(userId);
        if (profile == null) {
            return Result.fail(404, "画像不存在");
        }
        return Result.ok(profile);
    }

    // ==================== 私有方法 ====================

    /** 获取或创建画像专用会话 */
    private Conversation getOrCreateProfileConversation(Long userId) {
        // 查找已有的活跃画像会话
        List<Conversation> list = conversationService.listByUserId(userId);
        for (Conversation conv : list) {
            if ("active".equals(conv.getStatus()) && "画像构建".equals(conv.getTitle())) {
                return conv;
            }
        }
        // 新建
        Conversation conv = new Conversation()
                .setUserId(userId)
                .setTitle("画像构建")
                .setStatus("active");
        conversationService.save(conv);
        return conv;
    }

    /** 加载历史消息 */
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

    /** 保存AI回复 */
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

    /** 更新会话标题 */
    private void updateConversationTitle(Long conversationId) {
        try {
            Conversation conv = conversationService.getById(conversationId);
            if (conv != null && "画像构建".equals(conv.getTitle())) {
                // 检查画像是否已构建完成
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

    /** 保存画像到数据库 */
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
