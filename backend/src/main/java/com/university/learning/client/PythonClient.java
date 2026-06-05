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

    public SseEmitter unifiedChatStream(Long userId, String message, Consumer<Map<String, Object>> onDone) {
        Map<String, Object> request = new HashMap<>();
        request.put("user_id", userId);
        request.put("message", message);

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

    public SseEmitter tutorChatStream(Long userId,
                                      String content,
                                      String conversationId,
                                      Map<String, Object> profile) {
        Map<String, Object> request = new HashMap<>();
        request.put("user_id", userId);

        List<Map<String, String>> messages = new ArrayList<>();
        Map<String, String> msg = new HashMap<>();
        msg.put("role", "user");
        msg.put("content", content);
        messages.add(msg);
        request.put("messages", messages);

        request.put("conversation_id", conversationId != null ? conversationId : "");
        request.put("student_profile", profile != null ? profile : new HashMap<>());

        return createSseEmitter(BASE_URL + "/tutor/chat", request, null);
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
                    boolean streamEnded = false;

                    while (!streamEnded && (line = reader.readLine()) != null) {
                        if (line.startsWith("data: ")) {
                            String data = line.substring(6);
                            dataBuffer.append(data);
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
                                } else if ("done".equals(type)) {
                                    streamEnded = true;
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

                    if (onDone != null && !collectedData.isEmpty()) {
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