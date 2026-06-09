package com.university.learning.controller;

import com.university.learning.client.PythonClient;
import com.university.learning.entity.Conversation;
import com.university.learning.entity.Message;
import com.university.learning.entity.Resource;
import com.university.learning.service.IConversationService;
import com.university.learning.service.IMessageService;
import com.university.learning.service.IResourceService;
import com.university.learning.utils.UserHolder;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.*;
import java.util.stream.Collectors;

/**
 * 统一对话入口 — AI自动识别意图
 *
 * 支持的意图（由Python AI自动检测）：
 *   tutor     → 答疑对话，文字回复
 *   resource  → 生成学习资源（课程文档/思维导图等），自动落库
 *   exercise  → 生成练习题，自动落库
 *   solve     → 分步解题
 *   research  → 学习路径规划
 *
 * 流程：用户发消息 → 自动创建/复用会话 → 加载历史 → 调AI(SSE)
 *       → AI回复文字+自动识别意图生成内容 → 全部落库
 */
@Slf4j
@RestController
@RequestMapping("/api/chat")
@RequiredArgsConstructor
public class ChatController {

    private final PythonClient pythonClient;
    private final IResourceService resourceService;
    private final IConversationService conversationService;
    private final IMessageService messageService;

    /**
     * 统一对话入口
     * 请求体: { "message": "...", "conversation_id": 1(可选) }
     */
    @PostMapping
    public SseEmitter chat(@RequestBody Map<String, Object> request) {
        Long userId = getUserId();
        String message = (String) request.get("message");
        Long conversationId = request.get("conversation_id") != null
                ? Long.valueOf(request.get("conversation_id").toString()) : null;

        // 1. 获取或创建会话
        Conversation conversation = getOrCreateConversation(userId, conversationId, message);
        final Long finalConvId = conversation.getId();

        // 2. 保存用户消息
        messageService.save(new Message()
                .setConversationId(finalConvId)
                .setRole("user")
                .setContent(message)
                .setMode("chat"));

        // 3. 加载历史消息作为上下文
        List<Map<String, Object>> history = loadHistory(finalConvId, 50);

        // 4. 调用AI（mode=auto，AI自动识别意图）
        return pythonClient.unifiedChatStream(userId, message, finalConvId, history, (doneData) -> {
            // 5. 处理AI回复 — 按实际意图分别处理
            String detectedMode = detectMode(doneData);
            saveAiResponse(finalConvId, doneData, detectedMode);
            saveGeneratedContent(userId, doneData);
            updateConversationTitle(finalConvId, message);
        });
    }

    // ==================== 会话管理 ====================

    private Conversation getOrCreateConversation(Long userId, Long conversationId, String firstMessage) {
        if (conversationId != null) {
            Conversation existing = conversationService.getById(conversationId);
            if (existing != null && existing.getUserId().equals(userId)) {
                return existing;
            }
        }
        Conversation conv = new Conversation()
                .setUserId(userId)
                .setTitle(firstMessage.length() > 20 ? firstMessage.substring(0, 20) : firstMessage)
                .setStatus("active");
        conversationService.save(conv);
        log.info("创建新会话: id={}", conv.getId());
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

    private void updateConversationTitle(Long conversationId, String firstMessage) {
        try {
            Conversation conv = conversationService.getById(conversationId);
            if (conv != null && "新对话".equals(conv.getTitle()) && firstMessage != null) {
                String title = firstMessage.length() > 30 ? firstMessage.substring(0, 30) : firstMessage;
                conv.setTitle(title);
                conversationService.updateById(conv);
            }
        } catch (Exception e) {
            log.error("更新会话标题失败", e);
        }
    }

    // ==================== AI回复处理 ====================

    /** 检测AI实际使用的模式（从done事件中推断） */
    private String detectMode(Map<String, Object> doneData) {
        // 先检查嵌套的data字段（resource模式用StreamEvent包装）
        Map<String, Object> innerData = getInnerData(doneData);

        // resource模式：有content_blocks
        if (hasContent(doneData, "content_blocks") || hasContent(innerData, "content_blocks")) {
            return "resource";
        }
        // exercise模式：有questions
        if (hasContent(doneData, "questions") || hasContent(innerData, "questions")) {
            return "exercise";
        }
        // solve模式：有steps或confidence
        if (doneData.containsKey("confidence") || doneData.containsKey("steps")) {
            return "solve";
        }
        // 默认tutor
        return "tutor";
    }

    /** 提取嵌套的data子对象（StreamEvent格式） */
    @SuppressWarnings("unchecked")
    private Map<String, Object> getInnerData(Map<String, Object> doneData) {
        Object data = doneData.get("data");
        if (data instanceof Map) {
            return (Map<String, Object>) data;
        }
        return Collections.emptyMap();
    }

    private boolean hasContent(Map<String, Object> map, String key) {
        Object val = map.get(key);
        if (val instanceof List) {
            return !((List<?>) val).isEmpty();
        }
        return val != null;
    }

    /** 保存AI回复文字到消息表 */
    private void saveAiResponse(Long conversationId, Map<String, Object> doneData, String mode) {
        try {
            String response = extractResponseText(doneData);
            if (response.isEmpty()) {
                response = "[AI已回复]";
            }

            messageService.save(new Message()
                    .setConversationId(conversationId)
                    .setRole("assistant")
                    .setContent(response)
                    .setMode(mode));
        } catch (Exception e) {
            log.error("保存AI回复失败: convId={}", conversationId, e);
        }
    }

    /** 从done事件中提取AI回复文字 */
    private String extractResponseText(Map<String, Object> doneData) {
        // 1. SSE累积的完整文字（token事件拼合）
        String text = (String) doneData.get("_response_text");
        if (text != null && !text.isEmpty()) return text;

        // 2. done事件顶层的response字段
        text = (String) doneData.getOrDefault("response", "");
        if (!text.isEmpty()) return text;

        // 3. 嵌套data中的response字段（resource模式）
        Map<String, Object> inner = getInnerData(doneData);
        text = (String) inner.getOrDefault("response", "");
        if (!text.isEmpty()) return text;

        // 4. resource/exercise模式没有流式文字时，给个描述
        if (hasContent(doneData, "content_blocks") || hasContent(inner, "content_blocks")) {
            return "已生成学习资源，请查看";
        }
        if (hasContent(doneData, "questions") || hasContent(inner, "questions")) {
            return "已生成练习题，请作答";
        }

        return "";
    }

    // ==================== 内容落库 ====================

    /**
     * 保存AI自动生成的资源/习题到数据库
     * 兼容两种done事件格式：
     *   resource模式: {type:"done", data:{content_blocks:[...], questions:[...]}}
     *   exercise模式: {type:"done", questions:[...]}
     */
    private void saveGeneratedContent(Long userId, Map<String, Object> doneData) {
        try {
            Map<String, Object> inner = getInnerData(doneData);

            // 从顶层或嵌套data中提取
            List<Map<String, Object>> contentBlocks = extractList(doneData, inner, "content_blocks");
            List<Map<String, Object>> questions = extractList(doneData, inner, "questions");

            // 提取主题
            String topic = (String) doneData.getOrDefault("topic",
                    inner.getOrDefault("topic", "未知主题"));

            // 保存学习资源
            if (contentBlocks != null && !contentBlocks.isEmpty()) {
                for (Map<String, Object> block : contentBlocks) {
                    Resource resource = new Resource();
                    resource.setUserId(userId);
                    resource.setType((String) block.getOrDefault("type", "course_doc"));
                    resource.setTopic(topic);
                    resource.setTitle((String) block.getOrDefault("title", topic));
                    resource.setContentJson(block);
                    resourceService.save(resource);
                }
                log.info("AI自动生成资源已保存: userId={}, topic={}, count={}",
                        userId, topic, contentBlocks.size());
            }

            // 保存练习题
            if (questions != null && !questions.isEmpty()) {
                Resource resource = new Resource();
                resource.setUserId(userId);
                resource.setType("exercise");
                resource.setTopic(topic);
                resource.setTitle(topic + " 练习题");
                Map<String, Object> contentJson = new LinkedHashMap<>();
                contentJson.put("questions", questions);
                contentJson.put("count", questions.size());
                resource.setContentJson(contentJson);
                resourceService.save(resource);
                log.info("AI自动生成习题已保存: userId={}, topic={}, count={}",
                        userId, topic, questions.size());
            }
        } catch (Exception e) {
            log.error("自动保存生成内容失败: userId={}", userId, e);
        }
    }

    /** 从顶层和嵌套data中提取列表字段，优先取非空的 */
    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> extractList(Map<String, Object> top,
                                                   Map<String, Object> inner,
                                                   String key) {
        Object val = top.get(key);
        if (val instanceof List && !((List<?>) val).isEmpty()) {
            return (List<Map<String, Object>>) val;
        }
        val = inner.get(key);
        if (val instanceof List && !((List<?>) val).isEmpty()) {
            return (List<Map<String, Object>>) val;
        }
        return null;
    }

    private Long getUserId() {
        return UserHolder.getUser().getId();
    }
}
