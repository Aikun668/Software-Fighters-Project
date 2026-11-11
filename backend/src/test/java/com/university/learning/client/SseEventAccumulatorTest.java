package com.university.learning.client;

import org.junit.jupiter.api.Test;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SseEventAccumulatorTest {

    @Test
    void errorDoesNotEndTheStreamAndDoneStillCarriesTheConversation() {
        SseEventAccumulator accumulator = new SseEventAccumulator();
        Map<String, Object> token = event("token");
        token.put("content", "半截坏文本");
        assertTrue(accumulator.accept(token, 22L));

        Map<String, Object> error = event("error");
        error.put("content", "刚才没写完，你的问题还在，再发一次即可");
        error.put("code", "EMPTY_RESPONSE");
        assertTrue(accumulator.accept(error, 22L));
        assertEquals(22L, error.get("conversation_id"));

        Map<String, Object> done = event("done");
        done.put("summary", "failed");
        assertFalse(accumulator.accept(done, 22L));

        Map<String, Object> payload = accumulator.callbackPayload(22L);
        assertEquals(Boolean.TRUE, payload.get("_stream_error"));
        assertEquals("刚才没写完，你的问题还在，再发一次即可", payload.get("_error_content"));
        assertEquals("EMPTY_RESPONSE", payload.get("_error_code"));
        assertEquals(22L, payload.get("conversation_id"));
        assertNull(payload.get("_response_text"));
    }

    @Test
    void errorWithoutDoneStillProducesAPersistablePayload() {
        SseEventAccumulator accumulator = new SseEventAccumulator();
        Map<String, Object> error = event("error");
        error.put("content", "刚才没连上回答服务，你的问题还在，再发一次即可");
        assertTrue(accumulator.accept(error, 9L));

        Map<String, Object> payload = accumulator.callbackPayload(9L);
        assertEquals(Boolean.TRUE, payload.get("_stream_error"));
        assertEquals(9L, payload.get("conversation_id"));
        assertFalse(payload.containsKey("_response_text"));
    }

    @Test
    void successfulTokensAreKeptUntilDone() {
        SseEventAccumulator accumulator = new SseEventAccumulator();
        Map<String, Object> token = event("token");
        token.put("content", "你好");
        assertTrue(accumulator.accept(token, 3L));
        Map<String, Object> done = event("done");
        assertFalse(accumulator.accept(done, 3L));

        Map<String, Object> payload = accumulator.callbackPayload(3L);
        assertEquals("你好", payload.get("_response_text"));
        assertNull(payload.get("_stream_error"));
    }

    @Test
    void requestLogOmitsMessageTextAndImagePayloads() {
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("message", "这是不该进日志的原话");
        request.put("images", List.of("data:image/png;base64,SECRETDATA"));
        String described = SseEventAccumulator.describeRequest(request);
        assertFalse(described.contains("这是不该进日志的原话"));
        assertFalse(described.contains("SECRETDATA"));
        assertTrue(described.contains("messageChars="));
        assertTrue(described.contains("imageCount=1"));
    }

    private static Map<String, Object> event(String type) {
        Map<String, Object> event = new LinkedHashMap<>();
        event.put("type", type);
        return event;
    }
}
