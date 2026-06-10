package com.university.learning.client;

import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.*;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.BufferedReader;
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
     */
    public SseEmitter unifiedChatStream(Long userId, String message,
                                         Long conversationId,
                                         Map<String, Object> studentProfile,
                                         List<Map<String, Object>> historyMessages,
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

    public SseEmitter generateResourcesStream(Long userId,
                                              String topic,
                                              Map<String, Object> profile,
                                              Consumer<Map<String, Object>> onDone) {
        Map<String, Object> request = new HashMap<>();
        request.put("user_id", userId);
        request.put("topic", topic);
        request.put("student_profile", profile != null ? profile : new HashMap<>());

        return createSseEmitter(BASE_URL + "/resources/generate", request, onDone);
    }

    /**
     * 智能答疑（SSE流式）
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
        request.put("content", content);
        if (conversationId != null) {
            request.put("conversation_id", conversationId);
        }
        if (historyMessages != null && !historyMessages.isEmpty()) {
            request.put("messages", historyMessages);
        }
        request.put("student_profile", profile != null ? profile : new HashMap<>());

        return createSseEmitter(BASE_URL + "/tutor/chat", request, onDone);
    }

    public SseEmitter generateExercisesStream(Long userId,
                                              String topic,
                                              Integer count,
                                              String difficulty,
                                              Map<String, Object> profile,
                                              Consumer<Map<String, Object>> onDone) {
        Map<String, Object> request = new HashMap<>();
        request.put("user_id", userId);
        request.put("topic", topic);
        request.put("count", count != null ? count : 5);
        request.put("difficulty", difficulty != null ? difficulty : "medium");
        request.put("student_profile", profile != null ? profile : new HashMap<>());

        return createSseEmitter(BASE_URL + "/exercise/generate", request, onDone);
    }

    // ==================== 非流式接口 ====================

    public Map<String, Object> getProfileStatus(Long userId) {
        return doGet(BASE_URL + "/profile/workflow/status?user_id=" + userId);
    }

    public Map<String, Object> getLearningPath(Long userId) {
        return doGet(BASE_URL + "/path/" + userId);
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
     * 回归检测管线
     * 阶段1（无answers）: 出题 → 返回warmup题目
     * 阶段2（有answers）: 判分 + 重排 → 返回重排后的步骤
     */
    public Map<String, Object> regressionCheck(Long planId, Long userId,
                                                List<Map<String, Object>> answers) {
        Map<String, Object> request = new HashMap<>();
        request.put("user_id", userId);
        request.put("answers", answers != null ? answers : new ArrayList<>());
        return doPost(BASE_URL + "/plans/" + planId + "/regression-check", request);
    }

    /** 获取未来N天的复习日程（间隔重复提醒） */
    public Map<String, Object> getReviewSchedule(Long planId, Long userId, int daysAhead) {
        return doGet(BASE_URL + "/plans/" + planId + "/review-schedule?user_id=" + userId
                + "&days_ahead=" + daysAhead);
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

    // ==================== 仪表盘 & 会话管理 ====================

    /** 聚合学生仪表盘数据：画像 + 学习轨迹 + 能力评估 */
    public Map<String, Object> getUserDashboard(Long userId, String courseId) {
        return doGet(BASE_URL + "/user/dashboard?user_id=" + userId
                + "&course_id=" + (courseId != null ? courseId : "ai_intro"));
    }

    /** 获取会话学习总结卡片 */
    public Map<String, Object> getConversationSummary(Long conversationId, Long userId, String courseId) {
        return doGet(BASE_URL + "/conversations/" + conversationId + "/summary?user_id=" + userId
                + "&course_id=" + (courseId != null ? courseId : "ai_intro"));
    }

    /** 结束会话：生成总结卡片 + 触发摘要压缩 */
    public Map<String, Object> endConversation(Long conversationId, Long userId, String courseId) {
        return doPost(BASE_URL + "/conversations/" + conversationId + "/end?user_id=" + userId
                + "&course_id=" + (courseId != null ? courseId : "ai_intro"), new HashMap<>());
    }

    // ==================== 错题分析 ====================

    /** 对错题进行深度分析，解释错误原因和改进方法 */
    public Map<String, Object> errorAnalysis(List<Map<String, Object>> errors, int level) {
        Map<String, Object> request = new HashMap<>();
        request.put("errors", errors);
        request.put("level", level);
        return doPost(BASE_URL + "/exercise/error-analysis", request);
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
                conn.setReadTimeout(300000);

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
            throw new RuntimeException("大模型服务异常");
        }
    }

    private Map<String, Object> doGet(String url) {
        try {
            ResponseEntity<Map> response = restTemplate.exchange(url, HttpMethod.GET, null, Map.class);
            return response.getBody();
        } catch (Exception e) {
            log.error("调用Python失败: {}", url, e);
            throw new RuntimeException("大模型服务异常");
        }
    }
}