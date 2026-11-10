package com.university.learning.controller;

import com.university.learning.client.PythonClient;
import com.university.learning.dto.UserDTO;
import com.university.learning.entity.*;
import com.university.learning.service.*;
import com.university.learning.utils.UserHolder;
import org.junit.jupiter.api.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class ConversationMemoryContextTest {
    @AfterEach void logout() { UserHolder.removeUser(); }
    @Test void archiveSummaryCannotReplayForgottenFactsOrCredentials() {
        AgentMemoryService memory = new AgentMemoryService(new JdbcTemplate(new DriverManagerDataSource(
            "jdbc:h2:mem:summary_" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "")), true);
        memory.observe(1L, 10L, 100L, "记住：学习目标=通过软考");
        memory.observe(1L, 10L, 110L, "忘记：学习目标");
        IConversationService conversations = mock(IConversationService.class);
        IMessageService messages = mock(IMessageService.class);
        PythonClient python = mock(PythonClient.class);
        ConversationController controller = new ConversationController(conversations, messages, mock(IFileInfoService.class), python, memory);
        when(conversations.getById(10L)).thenReturn(new Conversation().setId(10L).setUserId(1L));
        when(messages.listByConversationId(10L)).thenReturn(List.of(
            new Message().setId(100L).setRole("user").setContent("记住：学习目标=通过软考"),
            new Message().setId(101L).setRole("assistant").setContent("你要通过软考"),
            new Message().setId(112L).setRole("user").setContent("密码是synthetic-password"),
            new Message().setId(113L).setRole("assistant").setContent("synthetic-password"),
            new Message().setId(120L).setRole("user").setContent("解释二分搜索")));
        doAnswer(inv -> {
            List<Map<String,Object>> history = inv.getArgument(1);
            assertEquals(1, history.size());
            assertEquals("解释二分搜索", history.get(0).get("content"));
            return Map.of("summary", "讨论二分搜索");
        }).when(python).getConversationSummary(eq(10L), anyList(), isNull());
        UserDTO user = new UserDTO(); user.setId(1L); UserHolder.saveUser(user);
        assertEquals(0, controller.endConversation(10L).getCode());
        verify(python).getConversationSummary(eq(10L), anyList(), isNull());
    }
}
