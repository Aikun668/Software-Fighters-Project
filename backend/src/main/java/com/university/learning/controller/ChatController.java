package com.university.learning.controller;

import com.university.learning.client.PythonClient;
import com.university.learning.dto.UnifiedChatRequest;
import com.university.learning.entity.Conversation;
import com.university.learning.entity.LearningPlan;
import com.university.learning.entity.Message;
import com.university.learning.entity.PlanStep;
import com.university.learning.entity.Resource;
import com.university.learning.entity.StudentProfile;
import com.university.learning.service.IConversationService;
import com.university.learning.service.ILearningPlanService;
import com.university.learning.service.IMessageService;
import com.university.learning.service.IPlanStepService;
import com.university.learning.service.IResourceService;
import com.university.learning.service.IStudentProfileService;
import com.university.learning.utils.UserHolder;
import io.swagger.v3.oas.annotations.Operation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.*;
import java.util.stream.Collectors;

/**
 * 统一对话入口 — AI自动识别意图

 * 支持的意图（由Python AI自动检测）：
 *   tutor     → 答疑对话，文字回复
 *   resource  → 生成学习资源（课程文档/思维导图等），自动落库
 *   exercise  → 生成练习题，自动落库
 *   solve     → 分步解题
 *   research  → 学习路径规划

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
    private final IStudentProfileService profileService;
    private final ILearningPlanService planService;
    private final IPlanStepService stepService;

    /**
     * 统一对话入口，AI自动识别意图（tutor/resource/exercise/solve/research）。
     */
    @Operation(summary = "统一对话入口", description ="支持的意图：tutor(答疑)、resource(生成资源)、exercise(练习题)、solve(解题)、research(路径规划)")
    @PostMapping
    public SseEmitter chat(@RequestBody UnifiedChatRequest request) {
        Long userId = getUserId();
        String message = request.getMessage();
        Long conversationId = request.getConversation_id();

        // 1. 获取或创建会话
        Conversation conversation = getOrCreateConversation(userId, conversationId, message);
        final Long finalConvId = conversation.getId();

        // 2. 保存用户消息（同时把本轮图片的 file_info.id 落库，
        //    否则历史回读时用户上传的图片永久丢失）
        messageService.save(new Message()
                .setConversationId(finalConvId)
                .setRole("user")
                .setContent(message)
                .setMode("chat")
                .setImageFileIds(request.getImage_file_ids()));

        // 3. 加载历史消息作为上下文
        List<Map<String, Object>> history = loadHistory(finalConvId, 50);

        // 4. 加载学生画像
        Map<String, Object> profileMap = buildProfileMap(userId);

        // 5. 调用AI（mode=auto，AI自动识别意图）
        return pythonClient.unifiedChatStream(userId, message, finalConvId, profileMap, history,
                request.getImages(), request.getStyle(), (doneData) -> {
            log.info("Chat done回调: convId={}, doneKeys={}", finalConvId, doneData.keySet());
            boolean failed = Boolean.TRUE.equals(doneData.get("_stream_error"));
            String detectedMode = failed ? "notice" : detectMode(doneData);
            log.info("Chat 检测到模式: {}", detectedMode);
            saveAiResponse(finalConvId, doneData, detectedMode);
            if (!failed && !"inquiry".equals(detectedMode)) {
                saveGeneratedContent(userId, message, doneData);
            }
            if (!failed) {
                saveResearchPlan(userId, doneData, detectedMode);
                saveProfileDelta(userId, doneData);
            }
            updateConversationTitle(finalConvId, message);
        });
    }

    // ==================== 会话管理 ====================

    private Conversation getOrCreateConversation(Long userId, Long conversationId, String firstMessage) {
        if (conversationId != null) {
            Conversation existing = conversationService.getById(conversationId);
            if (existing == null || !userId.equals(existing.getUserId())) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND, "会话不存在");
            }
            return existing;
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
        return messages.stream()
                .filter(ChatController::includeInModelHistory)
                .map(m -> {
                    Map<String, Object> item = new LinkedHashMap<>();
                    item.put("role", m.getRole());
                    item.put("content", m.getContent());
                    return item;
                }).collect(Collectors.toList());
    }

    /** 失败说明和历史占位符不能再被当成模型说过的话。 */
    static boolean includeInModelHistory(Message message) {
        if (message == null || "notice".equals(message.getMode())) {
            return false;
        }
        String content = message.getContent();
        if (content == null || content.isBlank()) {
            return false;
        }
        return !"[AI已回复]".equals(content.trim());
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
        // research模式：done事件中 mode:"research" 或 含有plan字段
        if ("research".equals(doneData.get("mode"))
                || doneData.get("plan") instanceof Map
                || doneData.get("_path_steps") instanceof List) {
            return "research";
        }
        // inquiry模式：Python返回追问
        if (doneData.get("is_clear") == Boolean.FALSE
                || "inquiry".equals(doneData.get("type"))) {
            return "inquiry";
        }
        // 检查嵌套的data字段（resource模式用StreamEvent包装）
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
            AssistantSave save = resolveAssistantSave(doneData, mode, extractResponseText(doneData));
            if (save == null) {
                log.info("本轮没有可展示正文，不写入占位助手消息: convId={}", conversationId);
                return;
            }
            messageService.save(new Message()
                    .setConversationId(conversationId)
                    .setRole("assistant")
                    .setContent(save.content())
                    .setMode(save.mode()));
        } catch (Exception e) {
            log.error("保存AI回复失败: convId={}", conversationId, e);
        }
    }

    record AssistantSave(String content, String mode) {
    }

    static AssistantSave resolveAssistantSave(Map<String, Object> doneData, String mode, String extracted) {
        if (Boolean.TRUE.equals(doneData.get("_stream_error"))) {
            Object text = doneData.get("_error_content");
            String notice = text == null ? "" : text.toString().trim();
            if (notice.isEmpty()) {
                notice = "刚才没写完，你的问题还在，再发一次即可";
            }
            return new AssistantSave(notice, "notice");
        }
        if (extracted == null || extracted.isBlank() || "[AI已回复]".equals(extracted.trim())) {
            return null;
        }
        return new AssistantSave(extracted, mode);
    }

    /** 从done事件中提取AI回复文字 */
    @SuppressWarnings("unchecked")
    private String extractResponseText(Map<String, Object> doneData) {
        // 1. SSE累积的完整文字（token事件拼合）
        String text = (String) doneData.get("_response_text");
        if (text != null && !text.isEmpty()) return text;

        // 2. Inquiry追问响应
        if (doneData.get("is_clear") == Boolean.FALSE
                || "inquiry".equals(doneData.get("type"))) {
            return formatInquiryText(doneData);
        }

        // 3. done事件顶层的response字段
        text = (String) doneData.getOrDefault("response", "");
        if (!text.isEmpty()) return text;

        // 4. 嵌套data中的response字段（resource模式）
        Map<String, Object> inner = getInnerData(doneData);
        text = (String) inner.getOrDefault("response", "");
        if (!text.isEmpty()) return text;

        // 5. research模式：从plan字段提取summary
        Object planObj = doneData.get("plan");
        if (planObj instanceof Map) {
            Map<?, ?> plan = (Map<?, ?>) planObj;
            int totalSteps = plan.get("total_steps") instanceof Number
                    ? ((Number) plan.get("total_steps")).intValue() : 0;
            return "已为您规划「" + plan.get("title") + "」学习路径，共 " + totalSteps + " 步，请查看";
        }
        if (doneData.get("_path_steps") instanceof List) {
            return "已为您规划学习路径，请查看";
        }

        // 6. resource/exercise模式没有流式文字时，给个描述
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
     * 保存AI自动生成的资源/习题到数据库。
     * topic 优先级：模型返回(inner.data.topic) > 模型返回(doneData.topic) > 用户消息 > "未知主题"
     *
     * @param userId      用户ID
     * @param userMessage 用户原始消息，作为 topic 的最后兜底
     * @param doneData    AI 模型返回的 done 事件数据
     */
    private void saveGeneratedContent(Long userId, String userMessage, Map<String, Object> doneData) {
        try {
            Map<String, Object> inner = getInnerData(doneData);

            // 从顶层或嵌套data中提取
            List<Map<String, Object>> contentBlocks = extractList(doneData, inner, "content_blocks");
            List<Map<String, Object>> questions = extractList(doneData, inner, "questions");

            log.info("saveGeneratedContent: hasContentBlocks={}, hasQuestions={}, innerKeys={}",
                    contentBlocks != null, questions != null, inner.keySet());

            // 提取主题：逐级 fallback，getOrDefault 不防 null 值，所以显式判空
            String topic = extractTopic(inner, doneData, userMessage);

            // 保存学习资源
            if (contentBlocks != null && !contentBlocks.isEmpty()) {
                for (Map<String, Object> block : contentBlocks) {
                    Resource resource = new Resource();
                    resource.setUserId(userId);
                    resource.setType((String) block.getOrDefault("type", "course_doc"));
                    resource.setTopic(topic);
                    // title 优先取模型返回的标题，回退到 topic
                    resource.setTitle(firstNonNull((String) block.get("title"), topic));
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

    /**
     * 按优先级提取 topic：inner.topic > doneData.topic > 用户消息 > "未知主题"。
     * 不使用 getOrDefault，因为 key 存在但值为 null 时 getOrDefault 返回 null。
     */
    private String extractTopic(Map<String, Object> inner, Map<String, Object> doneData, String userMessage) {
        String topic = (String) inner.get("topic");
        if (topic == null) {
            topic = (String) doneData.get("topic");
        }
        if (topic == null && userMessage != null && !userMessage.isBlank()) {
            // 用户消息截取前 30 字符作为主题兜底
            topic = userMessage.length() > 30 ? userMessage.substring(0, 30) : userMessage;
        }
        if (topic == null) {
            topic = "未知主题";
        }
        return topic;
    }

    /** 返回第一个非 null 的值，类似 SQL COALESCE。 */
    private String firstNonNull(String a, String b) {
        return a != null ? a : b;
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

    /**
     * 保存AI自动生成的学习计划（research意图）
     * Python done事件结构: { "type":"done", "mode":"research",
     *   "plan": { "title", "topic", "total_steps", "steps":[...], "concept_graph":{...} } }
     */
    @SuppressWarnings("unchecked")
    private void saveResearchPlan(Long userId, Map<String, Object> doneData, String mode) {
        if (!"research".equals(mode)) return;

        // 优先取 done事件中的 plan 字段，其次取 SSE 捕获的 _path_steps
        Object planObj = doneData.get("plan");
        List<Map<String, Object>> steps;
        String title;
        String topic;

        if (planObj instanceof Map) {
            Map<String, Object> plan = (Map<String, Object>) planObj;
            steps = (List<Map<String, Object>>) plan.get("steps");
            title = (String) plan.getOrDefault("title", "学习计划");
            topic = (String) plan.getOrDefault("topic", "");
        } else {
            // 兜底：从_path_steps取
            Object stepsObj = doneData.get("_path_steps");
            if (!(stepsObj instanceof List)) return;
            steps = (List<Map<String, Object>>) stepsObj;
            title = "学习计划";
            topic = "";
        }

        if (steps == null || steps.isEmpty()) return;

        try {
            LearningPlan plan = new LearningPlan()
                    .setUserId(userId)
                    .setCourseId("ai_intro")
                    .setTitle(title)
                    .setStatus("in_progress")
                    .setTotalSteps(steps.size())
                    .setCompletedSteps(0);
            planService.save(plan);

            // concept_graph 节点映射：name → id
            Map<String, String> nodeIdMap = new HashMap<>();
            if (planObj instanceof Map) {
                Map<String, Object> planMap = (Map<String, Object>) planObj;
                Object cg = planMap.get("concept_graph");
                if (cg instanceof Map) {
                    Object nodes = ((Map<?, ?>) cg).get("nodes");
                    if (nodes instanceof List) {
                        for (Object n : (List<?>) nodes) {
                            if (n instanceof Map) {
                                Map<?, ?> nm = (Map<?, ?>) n;
                                String name = (String) nm.get("name");
                                String nid = (String) nm.get("id");
                                if (name != null && nid != null) nodeIdMap.put(name, nid);
                            }
                        }
                    }
                }
            }

            for (Map<String, Object> s : steps) {
                String stepTopic = (String) s.getOrDefault("topic", "");
                PlanStep step = new PlanStep()
                        .setPlanId(plan.getId())
                        .setNodeId(nodeIdMap.getOrDefault(stepTopic, ""))
                        .setTopic(stepTopic)
                        .setOrder(toInt(s.get("order"), 0))
                        .setStatus((String) s.getOrDefault("status", "pending"))
                        .setNodeType("learn")
                        .setEstimatedDays(toInt(s.get("estimated_days"), 1))
                        .setTopicDifficulty(3);
                stepService.save(step);
            }

            log.info("AI自动生成学习计划已保存: userId={}, planId={}, topic={}, steps={}",
                    userId, plan.getId(), topic, steps.size());
        } catch (Exception e) {
            log.error("保存AI学习计划失败: userId={}", userId, e);
        }
    }

    /** 格式化inquiry追问文字 */
    @SuppressWarnings("unchecked")
    private String formatInquiryText(Map<String, Object> doneData) {
        Object qs = doneData.get("questions");
        if (qs instanceof List && !((List<?>) qs).isEmpty()) {
            StringBuilder sb = new StringBuilder("请确认以下信息：\n");
            for (Object q : (List<?>) qs) {
                if (q instanceof Map) {
                    Map<?, ?> m = (Map<?, ?>) q;
                    Object text = m.get("text");
                    if (text == null) text = m.get("question");
                    if (text != null) sb.append("- ").append(text).append("\n");
                } else if (q instanceof String) {
                    sb.append("- ").append(q).append("\n");
                }
            }
            return sb.toString();
        }
        Object topic = doneData.get("clarified_topic");
        return topic != null ? "请确认您想学习「" + topic + "」相关内容？" : "请提供更详细的学习需求";
    }

    /** 构建学生画像Map */
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
        if (profile.getRawProfileJson() instanceof Map<?, ?> raw && raw.get("last_extracted_msg_index") != null) {
            map.put("last_extracted_msg_index", raw.get("last_extracted_msg_index"));
        }
        return map;
    }

    /**
     * 保存AI在对话中被动提取的画像增量
     * Python TutorAgent 在 done 事件中附带 profile_delta
     */
    @SuppressWarnings("unchecked")
    private void saveProfileDelta(Long userId, Map<String, Object> doneData) {
        Object delta = doneData.get("profile_delta");
        if (!(delta instanceof Map)) return;

        Map<String, Object> deltaMap = (Map<String, Object>) delta;
        if (deltaMap.isEmpty()) return;

        try {
            StudentProfile profile = profileService.getByUserId(userId);
            if (profile == null) {
                profile = new StudentProfile();
                profile.setUserId(userId);
            }

            if (deltaMap.containsKey("knowledge_base")) {
                profile.setKnowledgeBase(toInteger(deltaMap.get("knowledge_base")));
            }
            if (deltaMap.containsKey("cognitive_style")) {
                profile.setCognitiveStyle((String) deltaMap.get("cognitive_style"));
            }
            if (deltaMap.containsKey("learning_goal")) {
                profile.setLearningGoal((String) deltaMap.get("learning_goal"));
            }
            if (deltaMap.containsKey("weak_points")) {
                profile.setWeakPoints(deltaMap.get("weak_points"));
            }
            if (deltaMap.containsKey("learning_pace")) {
                profile.setLearningPace((String) deltaMap.get("learning_pace"));
            }
            if (deltaMap.containsKey("interest_direction")) {
                profile.setInterestDirection(deltaMap.get("interest_direction"));
            }

            // 保存完整画像快照
            Map<String, Object> rawProfile = new HashMap<>(buildProfileMap(userId));
            rawProfile.putAll(deltaMap);
            profile.setRawProfileJson(rawProfile);

            profileService.saveOrUpdateProfile(userId, profile);
            log.info("画像被动更新: userId={}, changedFields={}", userId, deltaMap.keySet());
        } catch (Exception e) {
            log.error("被动保存画像失败: userId={}", userId, e);
        }
    }

    private int toInt(Object value, int defaultValue) {
        if (value instanceof Number) return ((Number) value).intValue();
        if (value instanceof String) {
            try { return Integer.parseInt((String) value); } catch (NumberFormatException e) { }
        }
        return defaultValue;
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
