package com.university.learning.controller;
import com.university.learning.client.PythonClient;
import com.university.learning.dto.UnifiedChatRequest;
import com.university.learning.dto.UserDTO;
import com.university.learning.entity.Conversation;
import com.university.learning.entity.Message;
import com.university.learning.service.*;
import com.university.learning.utils.UserHolder;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
class ChatControllerHistoryTest {
  @Test void snapshotsPriorTurnsBeforeSavingCurrentAndPreservesRepeatedQuestions() {
    PythonClient python = mock(PythonClient.class);
    IConversationService conversations = mock(IConversationService.class);
    IMessageService messages = mock(IMessageService.class);
    ChatController controller = new ChatController(python, mock(IResourceService.class), conversations,
        messages, mock(IStudentProfileService.class), mock(ILearningPlanService.class), mock(IPlanStepService.class),
        new AgentMemoryService(null, false));
    Conversation conversation = new Conversation().setUserId(1L); conversation.setId(7L);
    when(conversations.getById(7L)).thenReturn(conversation);
    List<Message> stored = new ArrayList<>();
    stored.add(new Message().setRole("user").setContent("same question"));
    stored.add(new Message().setRole("assistant").setContent("previous answer"));
    when(messages.listByConversationId(7L)).thenAnswer(inv -> new ArrayList<>(stored));
    when(messages.save(any(Message.class))).thenAnswer(inv -> { stored.add(inv.getArgument(0)); return true; });
    doAnswer(inv -> {
      List<Map<String,Object>> history = inv.getArgument(4);
      assertEquals(2, history.size());
      assertEquals("same question", history.get(0).get("content"));
      assertEquals("previous answer", history.get(1).get("content"));
      assertEquals("same question", inv.getArgument(1));
      return null;
    }).when(python).unifiedChatStream(any(),any(),any(),any(),any(),any(),any(),any());
    UserDTO user = new UserDTO(); user.setId(1L); UserHolder.saveUser(user);
    try {
      UnifiedChatRequest request = new UnifiedChatRequest();
      request.setMessage("same question"); request.setConversation_id(7L);
      controller.chat(request);
      verify(python).unifiedChatStream(any(),any(),any(),any(),any(),any(),any(),any());
      assertEquals(3, stored.size());
    } finally { UserHolder.removeUser(); }
  }
}
