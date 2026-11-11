package com.university.learning.controller;

import com.university.learning.entity.Conversation;
import com.university.learning.entity.Message;
import com.university.learning.service.IConversationService;
import com.university.learning.service.ILearningPlanService;
import com.university.learning.service.IMessageService;
import com.university.learning.service.IPlanStepService;
import com.university.learning.service.IResourceService;
import com.university.learning.service.IStudentProfileService;
import com.university.learning.client.PythonClient;
import com.university.learning.dto.UnifiedChatRequest;
import com.university.learning.dto.UserDTO;
import com.university.learning.utils.UserHolder;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ChatTurnPersistenceTest {

    @AfterEach
    void clearUser() {
        UserHolder.removeUser();
    }

    @Test
    void errorTurnIsStoredAsNoticeAndNotFedBackToTheModel() {
        ChatController.AssistantSave save = ChatController.resolveAssistantSave(
                Map.of("_stream_error", true, "_error_content", "刚才没写完，你的问题还在，再发一次即可"),
                "tutor",
                "半截坏文本");
        assertEquals("notice", save.mode());
        assertEquals("刚才没写完，你的问题还在，再发一次即可", save.content());

        Message notice = new Message().setRole("assistant").setMode("notice").setContent(save.content());
        Message placeholder = new Message().setRole("assistant").setMode("tutor").setContent("[AI已回复]");
        Message real = new Message().setRole("assistant").setMode("tutor").setContent("进程是正在运行的程序。");
        assertFalse(ChatController.includeInModelHistory(notice));
        assertFalse(ChatController.includeInModelHistory(placeholder));
        assertTrue(ChatController.includeInModelHistory(real));
    }

    @Test
    void emptySuccessDoesNotInventAReply() {
        assertNull(ChatController.resolveAssistantSave(Map.of("type", "done"), "tutor", ""));
        assertNull(ChatController.resolveAssistantSave(Map.of("type", "done"), "tutor", "[AI已回复]"));
    }

    @Test
    void foreignConversationIsRejectedBeforeTheUserMessageIsSaved() {
        UserDTO user = new UserDTO();
        user.setId(2L);
        UserHolder.saveUser(user);

        IConversationService conversations = mock(IConversationService.class);
        IMessageService messages = mock(IMessageService.class);
        Conversation foreign = new Conversation().setId(9L).setUserId(1L);
        when(conversations.getById(9L)).thenReturn(foreign);

        ChatController controller = new ChatController(
                mock(PythonClient.class),
                mock(IResourceService.class),
                conversations,
                messages,
                mock(IStudentProfileService.class),
                mock(ILearningPlanService.class),
                mock(IPlanStepService.class));

        UnifiedChatRequest request = new UnifiedChatRequest();
        request.setMessage("这是别人的会话");
        request.setConversation_id(9L);

        ResponseStatusException error = assertThrows(ResponseStatusException.class, () -> controller.chat(request));
        assertEquals(404, error.getStatusCode().value());
        verify(messages, never()).save(org.mockito.ArgumentMatchers.any());
    }
}
