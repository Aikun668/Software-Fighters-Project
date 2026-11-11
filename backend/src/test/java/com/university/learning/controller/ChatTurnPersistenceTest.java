package com.university.learning.controller;

import com.university.learning.entity.Message;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 移植 PR #2「失败的聊天也留在当前会话里」的两条语义到活路径：
 * 空回复不得编造 [AI已回复] 占位；失败轮落成提示，且提示不进模型历史。
 */
class ChatTurnPersistenceTest {

    @Test
    void errorTurnIsStoredAsANoticeNotAsPartialText() {
        ChatController.AssistantSave save = ChatController.resolveAssistantSave(
                Map.of("_stream_error", Boolean.TRUE,
                        "_error_content", "刚才没写完，你的问题还在，再发一次即可"),
                "tutor",
                "半截坏文本");

        assertEquals("notice", save.mode());
        assertEquals("刚才没写完，你的问题还在，再发一次即可", save.content());
    }

    @Test
    void errorTurnWithoutContentFallsBackToTheRetryNotice() {
        ChatController.AssistantSave save = ChatController.resolveAssistantSave(
                Map.of("_stream_error", Boolean.TRUE), "tutor", "");

        assertEquals("notice", save.mode());
        assertEquals(ChatController.RETRY_NOTICE, save.content());
    }

    @Test
    void emptySuccessDoesNotInventAReply() {
        assertNull(ChatController.resolveAssistantSave(Map.of("type", "done"), "tutor", ""));
        assertNull(ChatController.resolveAssistantSave(Map.of("type", "done"), "tutor", "[AI已回复]"));
        assertNull(ChatController.resolveAssistantSave(Map.of("type", "done"), "tutor", "   "));
    }

    @Test
    void normalTurnStillKeepsItsOwnMode() {
        ChatController.AssistantSave save = ChatController.resolveAssistantSave(
                Map.of("type", "done"), "tutor", "进程是正在运行的程序。");

        assertEquals("tutor", save.mode());
        assertEquals("进程是正在运行的程序。", save.content());
    }

    @Test
    void noticeAndPlaceholderAreNotFedBackToTheModel() {
        Message notice = new Message().setRole("assistant").setMode("notice").setContent(ChatController.RETRY_NOTICE);
        Message placeholder = new Message().setRole("assistant").setMode("tutor").setContent("[AI已回复]");
        Message real = new Message().setRole("assistant").setMode("tutor").setContent("进程是正在运行的程序。");
        Message user = new Message().setRole("user").setMode("tutor").setContent("什么是进程？");

        assertFalse(ChatController.includeInModelHistory(notice));
        assertFalse(ChatController.includeInModelHistory(placeholder));
        assertTrue(ChatController.includeInModelHistory(real));
        assertTrue(ChatController.includeInModelHistory(user));
    }
}
