package com.university.learning.client;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.university.learning.common.AIServiceException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.*;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.function.Consumer;

@Slf4j
@Component
@RequiredArgsConstructor
public class PythonClient {

    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper;

    private static final String BASE_URL = "http://127.0.0.1:8001/internal";

    // ==================== 统一对话入口 ====================

    /**
     * 统一对话入口（SSE流式）
     * @param conversationId 会话ID，null则自动创建
     * @param studentProfile 学生画像（可选）
     * @param historyMessages 历史消息列表（可选，用于上下文）
     * @param images 用户上传的图片URL列表（可选）
     * @param style 答疑风格："standard"(标准) / "socratic"(苏格拉底式引导)
     */
    public SseEmitter unifiedChatStream(Long userId, String message,
                                         Long conversationId,
                                         Map<String, Object> studentProfile,
                                         List<Map<String, Object>> historyMessages,
                                         List<String> images, String style,
                                         Consumer<Map<String, Object>> onDone) {
        Map<String, Object> request = new HashMap<>();
        request.put("user_id", userId);
        request.put("message", message);
        request.put("mode", "auto");
        request.put("student_profile", studentProfile != null ? studentProfile : new HashMap<>());
        if (conversationId != null) {
            request.put("conversation_id", conversationId);
        }
        if (historyMessages != null && !historyMessages.isEmpty()) {
            request.put("messages", historyMessages);
        }
        if (images != null && !images.isEmpty()) {
            // 将 MinIO 预签名 URL 转为 base64 data URI，避免 Python SSRF 拦截 localhost
            List<String> convertedImages = convertImagesForPython(images);
            request.put("images", convertedImages);
        }
        if (style != null) {
            request.put("style", style);
        }

        return createSseEmitter(BASE_URL + "/api/chat", request, onDone);
    }

    // ==================== 流式接口 ====================

    public SseEmitter buildProfileStream(Long userId,
                                         List<Map<String, String>> messages,
                                         Consumer<Map<String, Object>> onDone) {
        Map<String, Object> request = new HashMap<>();
        request.put("user_id", userId);
        request.put("messages", messages);

        return createSseEmitter(BASE_URL + "/profile/chat", request, onDone);
    }

    /**
     * 生成学习资源（SSE流式）
     * @param resourceType 资源类型：document/code/project/mindmap/flashcard/interactive_diagram，
     *                     不传则由AI自动判断
     */
    public SseEmitter generateResourcesStream(Long userId,
                                              String topic,
                                              String resourceType,
                                              Map<String, Object> profile,
                                              Consumer<Map<String, Object>> onDone) {
        Map<String, Object> request = new HashMap<>();
        request.put("user_id", userId);
        request.put("topic", topic);
        if (resourceType != null && !resourceType.isEmpty()) {
            request.put("resource_type", resourceType);
        }
        request.put("student_profile", profile != null ? profile : new HashMap<>());

        return createSseEmitter(BASE_URL + "/resources/generate", request, onDone);
    }

    /**
     * 智能答疑（SSE流式）
     * Python TutorChatRequest 模型要求 messages: list[dict] (min_length=1)
     * 将历史消息 + 当前用户消息合并为完整 messages 数组传入
     * @param conversationId 会话ID（可选）
     * @param historyMessages 历史消息列表（用于上下文）
     */
    public SseEmitter tutorChatStream(Long userId,
                                      String content,
                                      Long conversationId,
                                      List<Map<String, Object>> historyMessages,
                                      Map<String, Object> profile,
                                      Consumer<Map<String, Object>> onDone) {
        Map<String, Object> request = new HashMap<>();
        request.put("user_id", userId);
        // 构建完整消息列表：历史消息 + 当前用户消息
        List<Map<String, Object>> fullMessages = new ArrayList<>();
        if (historyMessages != null) {
            fullMessages.addAll(historyMessages);
        }
        Map<String, Object> userMsg = new HashMap<>();
        userMsg.put("role", "user");
        userMsg.put("content", content);
        fullMessages.add(userMsg);
        request.put("messages", fullMessages);
        if (conversationId != null) {
            request.put("conversation_id", conversationId);
        }
        request.put("student_profile", profile != null ? profile : new HashMap<>());

        return createSseEmitter(BASE_URL + "/tutor/chat", request, onDone);
    }

    /**
     * 生成练习题（SSE流式）
     * @param knowledgeNodeId 知识图谱节点ID（优先于topic）
     * @param strategy 出题策略：weakness(薄弱点)/review(错题同类)/new(新题)
     */
    public SseEmitter generateExercisesStream(Long userId,
                                              String topic,
                                              String knowledgeNodeId,
                                              String strategy,
                                              Integer count,
                                              String difficulty,
                                              Map<String, Object> profile,
                                              Consumer<Map<String, Object>> onDone) {
        Map<String, Object> request = new HashMap<>();
        request.put("user_id", userId);
        request.put("topic", topic != null ? topic : "");
        if (knowledgeNodeId != null && !knowledgeNodeId.isEmpty()) {
            request.put("knowledge_node_id", knowledgeNodeId);
        }
        if (strategy != null && !strategy.isEmpty()) {
            request.put("strategy", strategy);
        }
        request.put("count", count != null ? count : 5);
        request.put("difficulty", difficulty != null ? difficulty : "medium");
        request.put("student_profile", profile != null ? profile : new HashMap<>());

        return createSseEmitter(BASE_URL + "/exercise/generate", request, onDone);
    }

    // ==================== 非流式接口 ====================

    /**
     * 查询画像完整度，POST body 传 {user_id, student_profile}
     * @param studentProfile 学生画像快照（rawProfileJson），可为 null
     */
    public Map<String, Object> getProfileStatus(Long userId, Map<String, Object> studentProfile) {
        Map<String, Object> request = new HashMap<>();
        request.put("user_id", userId);
        request.put("student_profile", studentProfile != null ? studentProfile : new HashMap<>());
        return doPost(BASE_URL + "/profile/workflow/status", request);
    }

    /**
     * 获取学习路径规划，POST body 传 {user_id, topic, student_profile}
     * @param topic 学习主题，可为 null（Python 默认空字符串）
     * @param studentProfile 学生画像快照，可为 null
     */
    public Map<String, Object> getLearningPath(Long userId, String topic, Map<String, Object> studentProfile) {
        Map<String, Object> request = new HashMap<>();
        request.put("user_id", userId);
        request.put("topic", topic != null ? topic : "");
        request.put("student_profile", studentProfile != null ? studentProfile : new HashMap<>());
        return doPost(BASE_URL + "/path/" + userId, request);
    }

    public Map<String, Object> gradeExercise(String type, String userAnswer,
                                             String correctAnswer, List<String> choices,
                                             Boolean multi, Integer points,
                                             String referenceAnswer, String rubric) {
        Map<String, Object> request = new HashMap<>();
        request.put("type", type);
        request.put("user_answer", userAnswer);

        if ("choice".equals(type)) {
            request.put("correct_answer", correctAnswer);
            request.put("choices", choices);
            request.put("multi", multi != null ? multi : false);
            request.put("points", points != null ? points : 1);
        } else {
            request.put("reference_answer", referenceAnswer);
            request.put("rubric", rubric);
        }

        return doPost(BASE_URL + "/exercise/grade", request);
    }

    public Map<String, Object> getEvaluationReport(Long userId, Map<String, Object> evaluationResults) {
        Map<String, Object> request = new HashMap<>();
        request.put("user_id", userId);
        request.put("evaluation_results", evaluationResults);
        return doPost(BASE_URL + "/evaluation/report", request);
    }

    public Map<String, Object> exportPptx(List<Map<String, Object>> contentBlocks, String title) {
        Map<String, Object> request = new HashMap<>();
        request.put("content_blocks", contentBlocks);
        request.put("title", title != null ? title : "AI学习资源");
        return doPost(BASE_URL + "/resources/export-pptx", request);
    }

    // ==================== 解题（SSE流式） ====================

    /**
     * 分步解答数学/科学/逻辑问题（SSE流式）
     * SSE事件: steps(解题步骤) → token(解答文字) → confidence(置信度) → done
     */
    public SseEmitter solveStream(String question, String context, Long userId,
                                  Consumer<Map<String, Object>> onDone) {
        Map<String, Object> request = new HashMap<>();
        request.put("question", question);
        request.put("context", context != null ? context : "");
        request.put("user_id", userId);

        return createSseEmitter(BASE_URL + "/solve", request, onDone);
    }

    // ==================== 知识图谱 ====================

    /** 获取完整知识图谱（含用户掌握度+颜色映射） */
    public Map<String, Object> getKnowledgeGraph(String courseId, Map<String, Float> masteries) {
        Map<String, Object> request = new HashMap<>();
        request.put("masteries", masteries != null ? masteries : new HashMap<>());
        return doPost(BASE_URL + "/knowledge-graph/" + courseId, request);
    }

    /** 获取知识图谱节点卡片详情（子概念掌握度+图谱上下文+推荐动作） */
    public Map<String, Object> getNodeCard(String courseId, String nodeId,
                                            Map<String, Float> masteries,
                                            int totalExercises, String lastPracticed) {
        Map<String, Object> request = new HashMap<>();
        request.put("masteries", masteries != null ? masteries : new HashMap<>());
        request.put("total_exercises", totalExercises);
        request.put("last_practiced", lastPracticed != null ? lastPracticed : "");
        return doPost(BASE_URL + "/knowledge-graph/" + courseId + "/node/" + nodeId, request);
    }

    // ==================== 学习计划 ====================

    /** 一键生成学习路径 + 创建执行计划 */
    public Map<String, Object> createPlanFromPath(Long userId, String courseId,
                                                   Map<String, Object> studentProfile) {
        Map<String, Object> request = new HashMap<>();
        request.put("user_id", userId);
        request.put("course_id", courseId);
        request.put("student_profile", studentProfile != null ? studentProfile : new HashMap<>());
        return doPost(BASE_URL + "/plans/create-from-path", request);
    }

    // createPlan 在 Python 端不存在，已移除
    // 计划创建统一走 createPlanFromPath（Python 内部已包含路径生成）

    /** 查询计划状态（含软着陆触发检测） */
    public Map<String, Object> getPlanStatus(Map<String, Object> plan, List<Map<String, Object>> steps) {
        Map<String, Object> request = new HashMap<>();
        request.put("plan", plan != null ? plan : new HashMap<>());
        request.put("steps", steps != null ? steps : new ArrayList<>());
        return doPost(BASE_URL + "/plans/status", request);
    }

    // updatePlanProgress、resumePlan 在 Python 端不存在，已移除
    // 进度更新走 regressionCheck 和 NodeMasteryController.upsert

    /**
     * 回归检测管线，POST body 传 {user_id, answers, plan, steps, days_idle}
     * 阶段1（无answers）: 出题 → 返回warmup题目
     * 阶段2（有answers）: 判分 + 重排 → 返回重排后的步骤
     * @param plan 计划元数据（Java 传入），可为 null
     * @param steps 计划步骤列表（Java 传入），可为 null
     * @param daysIdle 计划空闲天数（Java 计算），默认 0
     */
    public Map<String, Object> regressionCheck(Long planId, Long userId,
                                                List<Map<String, Object>> answers,
                                                Map<String, Object> plan,
                                                List<Map<String, Object>> steps,
                                                int daysIdle) {
        Map<String, Object> request = new HashMap<>();
        request.put("user_id", userId);
        request.put("answers", answers != null ? answers : new ArrayList<>());
        request.put("plan", plan != null ? plan : new HashMap<>());
        request.put("steps", steps != null ? steps : new ArrayList<>());
        request.put("days_idle", daysIdle);
        return doPost(BASE_URL + "/plans/" + planId + "/regression-check", request);
    }

    /**
     * 获取未来N天的复习日程（间隔重复提醒），POST body 传 {steps, days_ahead}
     * @param steps 计划步骤列表（Java 传入），可为 null
     * @param daysAhead 未来 N 天，1-30
     */
    public Map<String, Object> getReviewSchedule(Long planId, List<Map<String, Object>> steps, int daysAhead) {
        Map<String, Object> request = new HashMap<>();
        request.put("steps", steps != null ? steps : new ArrayList<>());
        request.put("days_ahead", daysAhead);
        return doPost(BASE_URL + "/plans/" + planId + "/review-schedule", request);
    }

    // onNodeStatusChange 在 Python 端不存在，已移除
    // 节点状态变更通过 NodeMasteryController.upsert + PlanStep 更新完成

    // ==================== 追问解析（SSE流式） ====================

    /**
     * 接收用户对追问的回答，合并后生成资源（SSE流式）
     * SSE事件: 同资源生成 → done时包含 content_blocks, questions, resource_ids
     */
    public SseEmitter inquiryResolveStream(String originalMessage,
                                            List<String> answers,
                                            Long userId,
                                            Map<String, Object> studentProfile,
                                            List<Map<String, Object>> questions,
                                            List<String> suggestedTypes,
                                            String clarifiedTopic,
                                            Consumer<Map<String, Object>> onDone) {
        Map<String, Object> request = new HashMap<>();
        request.put("original_message", originalMessage);
        request.put("answers", answers);
        request.put("user_id", userId);
        request.put("student_profile", studentProfile != null ? studentProfile : new HashMap<>());
        request.put("questions", questions != null ? questions : new ArrayList<>());
        request.put("suggested_types", suggestedTypes != null ? suggestedTypes : new ArrayList<>());
        request.put("clarified_topic", clarifiedTopic != null ? clarifiedTopic : "");

        return createSseEmitter(BASE_URL + "/inquiry/resolve", request, onDone);
    }

    // ==================== 会话管理 ====================

    /**
     * 获取会话学习总结卡片，POST body 传 {messages, course_id}
     * @param messages 原始对话消息列表（Java 传入），不可为 null
     * @param courseId 课程 ID，可为 null（默认 ai_intro）
     */
    public Map<String, Object> getConversationSummary(Long conversationId, List<Map<String, Object>> messages, String courseId) {
        Map<String, Object> request = new HashMap<>();
        request.put("messages", messages != null ? messages : new ArrayList<>());
        request.put("course_id", courseId != null ? courseId : "ai_intro");
        return doPost(BASE_URL + "/conversations/" + conversationId + "/summary", request);
    }

    // ==================== 错题分析 ====================

    /** 对错题进行深度分析，解释错误原因和改进方法 */
    public Map<String, Object> errorAnalysis(List<Map<String, Object>> errors, int level) {
        Map<String, Object> request = new HashMap<>();
        request.put("errors", errors);
        request.put("level", level);
        return doPost(BASE_URL + "/exercise/error-analysis", request);
    }

    // ==================== 练习模块三服务（v3.0 新增） ====================

    /** 将练习题匹配到知识图谱节点 */
    public Map<String, Object> categorizeExercises(List<Map<String, Object>> exercises,
                                                    List<Map<String, Object>> knowledgeNodes,
                                                    String courseId) {
        Map<String, Object> request = new HashMap<>();
        request.put("exercises", exercises);
        request.put("knowledge_nodes", knowledgeNodes != null ? knowledgeNodes : new ArrayList<>());
        request.put("course_id", courseId != null ? courseId : "ai_intro");
        return doPost(BASE_URL + "/exercise/categorize", request);
    }

    /** 分析一次练习会话，返回逐知识点报告 + 掌握度更新建议 */
    public Map<String, Object> analyzeSession(List<Map<String, Object>> records,
                                               Map<String, Float> masteries,
                                               String courseId) {
        Map<String, Object> request = new HashMap<>();
        request.put("records", records);
        request.put("masteries", masteries != null ? masteries : new HashMap<>());
        request.put("course_id", courseId != null ? courseId : "ai_intro");
        return doPost(BASE_URL + "/exercise/session/analyze", request);
    }

    /** 练习仪表盘：练习统计 + 薄弱/强项 + 推荐节点 */
    public Map<String, Object> getExerciseDashboard(Long userId,
                                                     Map<String, Float> masteries,
                                                     List<Map<String, Object>> recentRecords,
                                                     String courseId) {
        Map<String, Object> request = new HashMap<>();
        request.put("user_id", userId);
        request.put("masteries", masteries != null ? masteries : new HashMap<>());
        request.put("recent_records", recentRecords != null ? recentRecords : new ArrayList<>());
        request.put("course_id", courseId != null ? courseId : "ai_intro");
        return doPost(BASE_URL + "/exercise/dashboard", request);
    }

    /** 练习数据反哺学生画像：合并薄弱点、强项、技能等级 */
    public Map<String, Object> enrichProfileByExercise(Long userId,
                                                        Map<String, Object> studentProfile,
                                                        List<Map<String, Object>> recentRecords,
                                                        Map<String, Object> sessionAnalysis) {
        Map<String, Object> request = new HashMap<>();
        request.put("user_id", userId);
        request.put("student_profile", studentProfile != null ? studentProfile : new HashMap<>());
        request.put("recent_records", recentRecords != null ? recentRecords : new ArrayList<>());
        request.put("session_analysis", sessionAnalysis != null ? sessionAnalysis : new HashMap<>());
        return doPost(BASE_URL + "/exercise/profile/enrich", request);
    }

    // ==================== 图谱分析/维护/可视化 ====================

    /** 从对话内容中提取知识节点（主节点+关联节点+候选节点） */
    public Map<String, Object> extractGraphNodes(String courseId, String userMessage,
                                                  String assistantReply, List<String> existingNodeIds) {
        Map<String, Object> request = new HashMap<>();
        request.put("course_id", courseId);
        request.put("user_message", userMessage);
        request.put("assistant_reply", assistantReply);
        request.put("existing_node_ids", existingNodeIds != null ? existingNodeIds : new ArrayList<>());
        return doPost(BASE_URL + "/graph/extract", request);
    }

    /** 批量更新图谱节点和边（add_node / add_edge） */
    public Map<String, Object> updateGraphNodes(String courseId,
                                                 List<Map<String, Object>> updates) {
        Map<String, Object> request = new HashMap<>();
        request.put("course_id", courseId);
        request.put("updates", updates != null ? updates : new ArrayList<>());
        return doPost(BASE_URL + "/graph/nodes", request);
    }

    /** 根据学习事件批量更新节点掌握度（Python计算，Java自行持久化） */
    public Map<String, Object> updateMasteries(String courseId,
                                                Map<String, Float> masteries,
                                                List<Map<String, Object>> events) {
        Map<String, Object> request = new HashMap<>();
        request.put("course_id", courseId != null ? courseId : "ai_intro");
        request.put("masteries", masteries != null ? masteries : new HashMap<>());
        request.put("events", events);
        return doPost(BASE_URL + "/graph/masteries", request);
    }

    /** 知识缺口分析：根据当前掌握度推荐下一个该学的节点 */
    public Map<String, Object> recommendNextNode(Map<String, Float> masteries, String courseId) {
        Map<String, Object> request = new HashMap<>();
        request.put("masteries", masteries != null ? masteries : new HashMap<>());
        request.put("course_id", courseId != null ? courseId : "ai_intro");
        return doPost(BASE_URL + "/graph/next-node", request);
    }

    /** 学习进度概要：全局掌握率 + 各分类统计 */
    public Map<String, Object> getGraphProgress(Map<String, Float> masteries, String courseId) {
        Map<String, Object> request = new HashMap<>();
        request.put("masteries", masteries != null ? masteries : new HashMap<>());
        request.put("course_id", courseId != null ? courseId : "ai_intro");
        return doPost(BASE_URL + "/graph/progress", request);
    }

    /** 前置条件检查：用户是否可以学习指定节点 */
    public Map<String, Object> checkPrerequisites(String nodeId,
                                                   Map<String, Float> masteries,
                                                   double threshold, String courseId) {
        Map<String, Object> request = new HashMap<>();
        request.put("node_id", nodeId);
        request.put("masteries", masteries != null ? masteries : new HashMap<>());
        request.put("threshold", threshold);
        request.put("course_id", courseId != null ? courseId : "ai_intro");
        return doPost(BASE_URL + "/graph/check-prerequisites", request);
    }

    /** 导出知识图谱为 Mermaid 流程图语法 */
    public Map<String, Object> exportMermaid(String courseId,
                                              Map<String, Float> masteries) {
        Map<String, Object> request = new HashMap<>();
        request.put("course_id", courseId != null ? courseId : "ai_intro");
        request.put("masteries", masteries != null ? masteries : new HashMap<>());
        return doPost(BASE_URL + "/graph/export-mermaid", request);
    }

    /** 返回带层级信息的图谱（前端分层布局） */
    public Map<String, Object> getLayeredGraph(Map<String, Float> masteries, String courseId) {
        Map<String, Object> request = new HashMap<>();
        request.put("masteries", masteries != null ? masteries : new HashMap<>());
        request.put("course_id", courseId != null ? courseId : "ai_intro");
        return doPost(BASE_URL + "/graph/layered", request);
    }

    // ==================== 计划模块扩展 ====================

    /** 查询计划状态（新路径：/plans/{plan_id}/status），含软着陆触发检测 */
    public Map<String, Object> getPlanStatusById(Long planId, Map<String, Object> plan,
                                                   List<Map<String, Object>> steps) {
        Map<String, Object> request = new HashMap<>();
        request.put("plan", plan != null ? plan : new HashMap<>());
        request.put("steps", steps != null ? steps : new ArrayList<>());
        return doPost(BASE_URL + "/plans/" + planId + "/status", request);
    }

    /** 完成学习步骤后触发巩固练习生成 */
    public Map<String, Object> completePlanStep(Long planId, Map<String, Object> step,
                                                 Map<String, Object> plan,
                                                 List<Map<String, Object>> steps) {
        Map<String, Object> request = new HashMap<>();
        request.put("step", step != null ? step : new HashMap<>());
        request.put("plan", plan != null ? plan : new HashMap<>());
        request.put("steps", steps != null ? steps : new ArrayList<>());
        return doPost(BASE_URL + "/plans/" + planId + "/complete-step", request);
    }

    /** 获取今日学习任务 + 资源建议 */
    public Map<String, Object> getTodayTasks(Long planId, Map<String, Object> plan,
                                              List<Map<String, Object>> steps,
                                              String startDate,
                                              Map<String, Float> masteries) {
        Map<String, Object> request = new HashMap<>();
        request.put("plan", plan != null ? plan : new HashMap<>());
        request.put("steps", steps != null ? steps : new ArrayList<>());
        if (startDate != null) {
            request.put("start_date", startDate);
        }
        request.put("masteries", masteries != null ? masteries : new HashMap<>());
        return doPost(BASE_URL + "/plans/" + planId + "/today", request);
    }

    /** 更新步骤进度 + 计算掌握度变化 */
    public Map<String, Object> updatePlanProgress(Long planId, Map<String, Object> plan,
                                                   List<Map<String, Object>> steps,
                                                   Long stepId, int stepOrder,
                                                   String status, String activityType,
                                                   Float score, Integer durationMinutes,
                                                   Map<String, Float> masteries) {
        Map<String, Object> request = new HashMap<>();
        request.put("plan", plan != null ? plan : new HashMap<>());
        request.put("steps", steps != null ? steps : new ArrayList<>());
        request.put("step_id", stepId != null ? stepId : 0);
        request.put("step_order", stepOrder);
        request.put("status", status);
        request.put("activity_type", activityType);
        request.put("score", score);
        request.put("duration_minutes", durationMinutes != null ? durationMinutes : 0);
        request.put("masteries", masteries != null ? masteries : new HashMap<>());
        return doPost(BASE_URL + "/plans/" + planId + "/progress", request);
    }

    /** 节点状态变更联动计划（同步计划步骤） */
    public Map<String, Object> onNodeStatusChange(Long planId, String nodeId,
                                                    String newStatus, String oldStatus,
                                                    Map<String, Object> plan,
                                                    List<Map<String, Object>> steps,
                                                    Map<String, Float> masteries) {
        Map<String, Object> request = new HashMap<>();
        request.put("node_id", nodeId);
        request.put("new_status", newStatus);
        request.put("old_status", oldStatus != null ? oldStatus : "");
        request.put("plan", plan != null ? plan : new HashMap<>());
        request.put("steps", steps != null ? steps : new ArrayList<>());
        request.put("masteries", masteries != null ? masteries : new HashMap<>());
        return doPost(BASE_URL + "/plans/" + planId + "/node-status-change", request);
    }

    // ==================== 资源导出 ====================

    /** 根据 content_blocks 导出 PDF 文件 */
    public Map<String, Object> exportPdf(List<Map<String, Object>> contentBlocks, String title) {
        Map<String, Object> request = new HashMap<>();
        request.put("content_blocks", contentBlocks);
        request.put("title", title != null ? title : "AI学习资源");
        return doPost(BASE_URL + "/resources/export-pdf", request);
    }

    // ==================== 图片转换 ====================

    /**
     * 将图片 URL 列表转为 Python 可接受的格式。
     * MinIO 预签名 URL 含 localhost 会被 Python SSRF 拦截，需先下载转 base64 data URI。
     * 已经是 data:image URI 或外部 http URL 的保持不变。
     */
    private List<String> convertImagesForPython(List<String> images) {
        List<String> result = new ArrayList<>();
        for (String img : images) {
            if (img == null || img.isEmpty()) continue;
            // 已是 data URI 或非 MinIO 内部 URL，直接透传
            if (img.startsWith("data:image/")) {
                result.add(img);
                continue;
            }
            // MinIO/localhost URL → 下载转 base64
            try {
                String base64 = downloadImageToBase64(img);
                result.add(base64);
            } catch (Exception e) {
                log.warn("图片转换失败，跳过: url={}", img, e);
            }
        }
        return result;
    }

    /** 从 URL 下载图片并转为 data:image/xxx;base64,... 格式 */
    private String downloadImageToBase64(String imageUrl) throws Exception {
        URL url = new URL(imageUrl);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setConnectTimeout(5000);
        conn.setReadTimeout(10000);
        conn.setRequestMethod("GET");

        String contentType = conn.getContentType();
        if (contentType == null || !contentType.startsWith("image/")) {
            contentType = "image/jpeg"; // 兜底
        }

        try (InputStream is = conn.getInputStream();
             ByteArrayOutputStream bos = new ByteArrayOutputStream()) {
            byte[] buf = new byte[8192];
            int n;
            while ((n = is.read(buf)) != -1) {
                bos.write(buf, 0, n);
            }
            String b64 = Base64.getEncoder().encodeToString(bos.toByteArray());
            return "data:" + contentType + ";base64," + b64;
        } finally {
            conn.disconnect();
        }
    }

    // ==================== 核心方法 ====================

    private SseEmitter createSseEmitter(String pythonUrl,
                                        Map<String, Object> request,
                                        Consumer<Map<String, Object>> onDone) {
        SseEmitter emitter = new SseEmitter(300000L);

        CompletableFuture.runAsync(() -> {
            HttpURLConnection conn = null;
            try {
                URL url = new URL(pythonUrl);
                conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setDoOutput(true);

                conn.setConnectTimeout(10000);
                conn.setReadTimeout(600000);

                String requestBody = objectMapper.writeValueAsString(request);
                log.info("调用Python: {} body={}", pythonUrl, requestBody);
                conn.getOutputStream().write(requestBody.getBytes());
                conn.getOutputStream().flush();

                int responseCode = conn.getResponseCode();
                if (responseCode != 200) {
                    InputStream errorStream = conn.getErrorStream();
                    if (errorStream != null) {
                        BufferedReader errorReader = new BufferedReader(new InputStreamReader(errorStream));
                        StringBuilder errorBody = new StringBuilder();
                        String line;
                        while ((line = errorReader.readLine()) != null) {
                            errorBody.append(line);
                        }
                        log.error("Python返回错误: code={}, body={}", responseCode, errorBody.toString());
                    }
                    emitter.completeWithError(new RuntimeException("Python返回" + responseCode));
                    return;
                }

                try (BufferedReader reader = new BufferedReader(
                        new InputStreamReader(conn.getInputStream()))) {

                    String line;
                    StringBuilder dataBuffer = new StringBuilder();
                    Map<String, Object> collectedData = new HashMap<>();
                    StringBuilder responseText = new StringBuilder();
                    boolean streamEnded = false;
                    boolean isSse = false;
                    StringBuilder jsonBody = new StringBuilder();

                    while (!streamEnded && (line = reader.readLine()) != null) {
                        if (line.startsWith("data: ")) {
                            isSse = true;
                            String data = line.substring(6);
                            dataBuffer.append(data);
                        } else if (!line.startsWith("data: ") && !line.isEmpty()) {
                            // 非SSE行，累积为JSON
                            jsonBody.append(line);
                        } else if (line.isEmpty() && dataBuffer.length() > 0) {
                            String eventData = dataBuffer.toString();
                            dataBuffer = new StringBuilder();

                            emitter.send(SseEmitter.event().data(eventData));

                            try {
                                Map<String, Object> event = objectMapper.readValue(eventData, Map.class);
                                String type = (String) event.get("type");

                                if ("meta".equals(type)) {
                                    collectedData.put("conversation_id", event.get("conversation_id"));
                                } else if ("profile_update".equals(type) || "profile_complete".equals(type)) {
                                    Object content = event.get("content");
                                    if (content instanceof Map) {
                                        collectedData.putAll((Map<String, Object>) content);
                                    }
                                } else if ("token".equals(type)) {
                                    // 累积流式文字
                                    Object tokenContent = event.get("content");
                                    if (tokenContent != null) {
                                        responseText.append(tokenContent.toString());
                                    }
                                } else if ("inquiry".equals(type)) {
                                    // 捕获inquiry追问数据
                                    collectedData.putAll(event);
                                } else if ("path".equals(type)) {
                                    // 捕获学习路径/研究模式的数据（兜底）
                                    collectedData.put("_path_steps", event.get("steps"));
                                    collectedData.put("_concept_graph", event.get("concept_graph"));
                                    collectedData.put("_path_response", event.get("response"));
                                } else if ("done".equals(type)) {
                                    streamEnded = true;
                                    // 注入累积的完整回复文字
                                    if (responseText.length() > 0) {
                                        event.put("_response_text", responseText.toString());
                                    }
                                    if (!collectedData.isEmpty()) {
                                        collectedData.forEach((k, v) -> {
                                            if (!event.containsKey(k)) {
                                                event.put(k, v);
                                            }
                                        });
                                    }
                                    collectedData = event;
                                } else if ("error".equals(type)) {
                                    streamEnded = true;
                                    log.error("Python返回错误: {}", event.get("content"));
                                }
                            } catch (Exception e) {
                                // token数据，忽略
                            }
                        }
                    }

                    // 非SSE响应：Python返回了普通JSON（如inquiry追问、错误等）
                    if (!isSse && jsonBody.length() > 0) {
                        try {
                            @SuppressWarnings("unchecked")
                            Map<String, Object> jsonResp = objectMapper.readValue(
                                    jsonBody.toString(), Map.class);
                            log.info("Python返回JSON(非SSE): keys={}", jsonResp.keySet());
                            // 提取data字段作为doneData传给回调
                            Object respData = jsonResp.get("data");
                            if (respData instanceof Map) {
                                @SuppressWarnings("unchecked")
                                Map<String, Object> dataMap = (Map<String, Object>) respData;
                                if (onDone != null) {
                                    onDone.accept(dataMap);
                                }
                            }
                        } catch (Exception e) {
                            log.error("解析Python JSON响应失败", e);
                        }
                    }

                    if (isSse && onDone != null && !collectedData.isEmpty()) {
                        try {
                            onDone.accept(collectedData);
                            log.info("回调执行成功");
                        } catch (Exception e) {
                            log.error("回调执行失败", e);
                        }
                    }
                }

                emitter.complete();
            } catch (Exception e) {
                log.error("SSE转发失败", e);
                emitter.completeWithError(e);
            } finally {
                if (conn != null) {
                    conn.disconnect();
                }
            }
        });

        emitter.onTimeout(() -> {
            log.warn("SSE超时");
            emitter.complete();
        });

        return emitter;
    }

    private Map<String, Object> doPost(String url, Map<String, Object> request) {
        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            String body = objectMapper.writeValueAsString(request);
            HttpEntity<String> entity = new HttpEntity<>(body, headers);
            ResponseEntity<Map> response = restTemplate.exchange(url, HttpMethod.POST, entity, Map.class);
            return response.getBody();
        } catch (Exception e) {
            log.error("调用Python失败: {}", url, e);
            throw new AIServiceException("大模型服务异常", e);
        }
    }

    private Map<String, Object> doGet(String url) {
        try {
            ResponseEntity<Map> response = restTemplate.exchange(url, HttpMethod.GET, null, Map.class);
            return response.getBody();
        } catch (Exception e) {
            log.error("调用Python失败: {}", url, e);
            throw new AIServiceException("大模型服务异常", e);
        }
    }
}