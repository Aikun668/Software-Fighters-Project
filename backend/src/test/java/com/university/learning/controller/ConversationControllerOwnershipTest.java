package com.university.learning.controller;

import com.university.learning.client.PythonClient;
import com.university.learning.common.GlobalExceptionHandler;
import com.university.learning.dto.UserDTO;
import com.university.learning.entity.Conversation;
import com.university.learning.service.*;
import com.university.learning.utils.UserHolder;
import org.junit.jupiter.api.*;
import org.springframework.web.server.ResponseStatusException;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class ConversationControllerOwnershipTest {
    private final IConversationService conversations = mock(IConversationService.class);
    private final IMessageService messages = mock(IMessageService.class);
    private final PythonClient python = mock(PythonClient.class);
    private final ConversationController controller = new ConversationController(conversations, messages,
            mock(IFileInfoService.class), python, new AgentMemoryService(null, false));

    @BeforeEach void login() {
        UserDTO user = new UserDTO(); user.setId(1L); UserHolder.saveUser(user);
        when(conversations.getById(8L)).thenReturn(new Conversation().setId(8L).setUserId(2L));
    }
    @AfterEach void logout() { UserHolder.removeUser(); }

    @Test void creationIgnoresSpoofedOwner() {
        Conversation created = (Conversation) controller.create(Map.of("user_id", 2L)).getData();
        assertEquals(1L, created.getUserId());
    }

    @Test void everyConversationReadAndWriteRejectsOtherOwnerBeforeSideEffects() {
        List<Runnable> attempts = List.of(
            () -> controller.getDetail(8L, 2L),
            () -> controller.update(8L, Map.of("title", "hijack")),
            () -> controller.getMessages(8L, null, 50),
            () -> controller.getMessagesRaw(8L, 0, 50),
            () -> controller.saveMessages(8L, Map.of("user_message", "hijack")),
            () -> controller.deleteConversation(8L),
            () -> controller.endConversation(8L));
        for (Runnable attempt : attempts) {
            ResponseStatusException error = assertThrows(ResponseStatusException.class, attempt::run);
            assertEquals(403, error.getStatusCode().value());
        }
        verifyNoInteractions(messages, python);
        verify(conversations, never()).updateById(any(Conversation.class));
        verify(conversations, never()).removeById(any(Long.class));
    }

    @Test void missingConversationReturns404() {
        ResponseStatusException error = assertThrows(ResponseStatusException.class,
            () -> controller.getMessages(99L, null, 50));
        assertEquals(404, error.getStatusCode().value());
    }

    @Test void missingIdentityCannotReadOrCreate() {
        UserHolder.removeUser();
        assertEquals(401, assertThrows(ResponseStatusException.class,
            () -> controller.create(Map.of("user_id", 1L))).getStatusCode().value());
        assertEquals(401, assertThrows(ResponseStatusException.class,
            () -> controller.getMessages(8L, null, 50)).getStatusCode().value());
    }

    @Test void ownershipFailureUsesHttp403RatherThanGeneric500() throws Exception {
        MockMvcBuilders.standaloneSetup(controller).setControllerAdvice(new GlobalExceptionHandler()).build()
            .perform(get("/api/conversations/8/messages")).andExpect(status().isForbidden());
    }
}
