package com.university.learning.client;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 把 Python 的 SSE 帧收成一次可落库的终态。
 *
 * error 不是读取终点：调度器在 error 之后还会再发 done。
 * 停在 error 上会丢掉会话 id，用户问题已经入库，助手回复却没有。
 */
final class SseEventAccumulator {

    static final String USER_RETRY = "刚才没写完，你的问题还在，再发一次即可";

    private final Map<String, Object> side = new LinkedHashMap<>();
    private final StringBuilder responseText = new StringBuilder();
    private Map<String, Object> terminal;
    private boolean sawDone;
    private boolean sawError;
    private boolean stopped;
    private String errorContent = "";
    private String errorCode;
    private String stopContent;
    private String stopCode;

    synchronized boolean accept(Map<String, Object> event, Object conversationId) {
        String type = event.get("type") instanceof String value ? value : "";
        switch (type) {
            case "meta" -> {
                if (event.get("conversation_id") != null) {
                    side.put("conversation_id", event.get("conversation_id"));
                }
            }
            case "profile_update", "profile_complete" -> {
                Object content = event.get("content");
                if (content instanceof Map<?, ?> map) {
                    for (Map.Entry<?, ?> entry : map.entrySet()) {
                        side.put(String.valueOf(entry.getKey()), entry.getValue());
                    }
                }
            }
            case "token" -> {
                Object tokenContent = event.get("content");
                if (tokenContent != null) {
                    responseText.append(tokenContent);
                }
            }
            case "content" -> {
                Object payload = event.get("data");
                if (payload instanceof Map<?, ?> payloadMap) {
                    Object text = payloadMap.get("response");
                    if (text == null) {
                        text = payloadMap.get("content");
                    }
                    if (text instanceof String value && !value.isBlank() && responseText.isEmpty()) {
                        responseText.append(value);
                    }
                }
            }
            case "inquiry" -> side.putAll(event);
            case "path" -> {
                side.put("_path_steps", event.get("steps"));
                side.put("_concept_graph", event.get("concept_graph"));
                side.put("_path_response", event.get("response"));
            }
            case "error" -> {
                sawError = true;
                Object content = event.get("content");
                if (content == null) {
                    content = event.get("message");
                }
                errorContent = content == null ? "" : content.toString();
                Object code = event.get("code");
                if (code != null) {
                    errorCode = code.toString();
                }
                if (conversationId != null && !event.containsKey("conversation_id")) {
                    event.put("conversation_id", conversationId);
                }
            }
            case "done" -> {
                sawDone = true;
                if (conversationId != null && !event.containsKey("conversation_id")) {
                    event.put("conversation_id", conversationId);
                }
                if (sawError) {
                    event.put("_stream_error", Boolean.TRUE);
                    event.put("_error_content", errorContent.isBlank() ? USER_RETRY : errorContent);
                    if (errorCode != null && !errorCode.isBlank()) {
                        event.put("_error_code", errorCode);
                    }
                } else if (!responseText.isEmpty()) {
                    event.put("_response_text", responseText.toString());
                }
                side.forEach((key, value) -> event.putIfAbsent(key, value));
                terminal = event;
                return false;
            }
            default -> {
            }
        }
        return true;
    }

    /** @return false when a terminal result was already recorded */
    synchronized boolean markStopped(String content, String code) {
        if (sawDone || stopped) {
            return false;
        }
        stopped = true;
        stopContent = content;
        stopCode = code;
        return true;
    }

    synchronized Map<String, Object> callbackPayload(Object conversationId) {
        if (terminal != null) {
            return terminal;
        }
        if (!sawError && !stopped) {
            return null;
        }
        Map<String, Object> synthetic = new LinkedHashMap<>();
        synthetic.put("type", "done");
        synthetic.put("_stream_error", Boolean.TRUE);
        String content = sawError && errorContent != null && !errorContent.isBlank()
                ? errorContent
                : (stopContent == null || stopContent.isBlank() ? USER_RETRY : stopContent);
        synthetic.put("_error_content", content);
        String code = sawError && errorCode != null && !errorCode.isBlank() ? errorCode : stopCode;
        if (code != null && !code.isBlank()) {
            synthetic.put("_error_code", code);
        }
        if (conversationId != null) {
            synthetic.put("conversation_id", conversationId);
        }
        side.forEach(synthetic::putIfAbsent);
        return synthetic;
    }

    static String describeRequest(Map<String, Object> request) {
        Object message = request.get("message");
        int chars = message == null ? 0 : message.toString().length();
        Object images = request.get("images");
        int imageCount = images instanceof java.util.List<?> list ? list.size() : 0;
        return "keys=" + request.keySet() + " messageChars=" + chars + " imageCount=" + imageCount;
    }
}
