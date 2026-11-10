package com.university.learning.controller;

import com.university.learning.client.PythonClient;
import com.university.learning.dto.*;
import com.university.learning.entity.*;
import com.university.learning.service.*;
import com.university.learning.utils.UserHolder;
import org.junit.jupiter.api.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.web.server.ResponseStatusException;
import java.util.*;
import java.util.function.Consumer;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class ChatControllerMemoryTest {
    private final PythonClient python = mock(PythonClient.class);
    private final IConversationService conversations = mock(IConversationService.class);
    private final IMessageService messages = mock(IMessageService.class);
    private final IStudentProfileService profiles = mock(IStudentProfileService.class);
    private final AgentMemoryService memory = new AgentMemoryService(new JdbcTemplate(new DriverManagerDataSource(
        "jdbc:h2:mem:chat_" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "")), true);
    private ChatController controller;
    @BeforeEach void setup() {
        controller = new ChatController(python, mock(IResourceService.class), conversations, messages, profiles,
            mock(ILearningPlanService.class), mock(IPlanStepService.class), memory);
        UserDTO user = new UserDTO(); user.setId(1L); UserHolder.saveUser(user);
        when(conversations.getById(10L)).thenReturn(new Conversation().setId(10L).setUserId(1L));
        when(conversations.getById(20L)).thenReturn(new Conversation().setId(20L).setUserId(2L));
        when(messages.listByConversationId(10L)).thenReturn(List.of(new Message().setId(90L).setRole("user").setContent("你好")));
        when(messages.save(any(Message.class))).thenAnswer(inv -> { ((Message) inv.getArgument(0)).setId(100L); return true; });
    }
    @AfterEach void logout() { UserHolder.removeUser(); }
    private UnifiedChatRequest request(long conv, String text) {
        UnifiedChatRequest request = new UnifiedChatRequest(); request.setConversation_id(conv); request.setMessage(text); return request;
    }

    @Test void suppliedForeignOrMissingConversationNeverFallsBackToCreate() {
        assertEquals(403, assertThrows(ResponseStatusException.class, () -> controller.chat(request(20L, "你好"))).getStatusCode().value());
        assertEquals(404, assertThrows(ResponseStatusException.class, () -> controller.chat(request(30L, "你好"))).getStatusCode().value());
        verify(conversations, never()).save(any(Conversation.class));
        verifyNoInteractions(messages, python);
    }

    @Test @SuppressWarnings("unchecked") void memoryUsesPersistedUserSourceAndNeverOldProfileOrCurrentInputHistory() {
        doAnswer(inv -> {
            Map<String,Object> profile = inv.getArgument(3);
            Map<String,Object> context = (Map<String,Object>) profile.get("_agent_memory");
            assertNotNull(context);
            assertEquals(1L, context.get("user_id"));
            assertEquals(10L, context.get("conversation_id"));
            List<Map<String,Object>> facts = (List<Map<String,Object>>) context.get("facts");
            assertEquals(100L, facts.get(0).get("source_message_id"));
            assertEquals("通过软考", facts.get(0).get("value"));
            List<Map<String,Object>> history = inv.getArgument(4);
            assertEquals(1, history.size()); assertEquals(90L, history.get(0).get("id"));
            assertEquals(Set.of("_agent_memory"), profile.keySet());
            ((Consumer<Map<String,Object>>) inv.getArgument(7)).accept(Map.of("response", "好的", "profile_delta", Map.of("learning_goal", "错误目标")));
            return null;
        }).when(python).unifiedChatStream(any(), any(), any(), any(), any(), any(), any(), any());
        controller.chat(request(10L, "我的学习目标是通过软考"));
        verifyNoInteractions(profiles);
    }

    @Test void failedMessagePersistenceDoesNotInvokeModelOrMemory() {
        when(messages.save(any(Message.class))).thenReturn(false);
        assertEquals(503, assertThrows(ResponseStatusException.class,
            () -> controller.chat(request(10L, "记住：目标=软考"))).getStatusCode().value());
        verifyNoInteractions(python);
    }
}
