package com.university.learning.controller;

import com.university.learning.client.PythonClient;
import com.university.learning.common.Result;
import com.university.learning.dto.UserDTO;
import com.university.learning.entity.Conversation;
import com.university.learning.service.IConversationService;
import com.university.learning.service.IFileInfoService;
import com.university.learning.service.IMessageService;
import com.university.learning.utils.UserHolder;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ConversationAccessTest {

    @AfterEach
    void clearUser() {
        UserHolder.removeUser();
    }

    @Test
    void readingAnotherUsersConversationReturnsNotFound() {
        UserDTO user = new UserDTO();
        user.setId(2L);
        UserHolder.saveUser(user);

        IConversationService conversations = mock(IConversationService.class);
        IMessageService messages = mock(IMessageService.class);
        when(conversations.getById(5L)).thenReturn(new Conversation().setId(5L).setUserId(1L));

        ConversationController controller = new ConversationController(
                conversations, messages, mock(IFileInfoService.class), mock(PythonClient.class));

        Result detail = controller.getDetail(5L);
        Result history = controller.getMessages(5L, null, 50);
        assertEquals(404, detail.getCode());
        assertEquals(404, history.getCode());
        verify(messages, never()).listByConversationId(5L);
        verify(messages, never()).listByConversationIdAndMode(org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.anyInt());
    }

    @Test
    void createIgnoresUserIdInTheBody() {
        UserDTO user = new UserDTO();
        user.setId(7L);
        UserHolder.saveUser(user);

        IConversationService conversations = mock(IConversationService.class);
        ConversationController controller = new ConversationController(
                conversations, mock(IMessageService.class), mock(IFileInfoService.class), mock(PythonClient.class));

        controller.create(Map.of("user_id", 1));

        org.mockito.ArgumentCaptor<Conversation> saved = org.mockito.ArgumentCaptor.forClass(Conversation.class);
        verify(conversations).save(saved.capture());
        assertEquals(7L, saved.getValue().getUserId());
    }
}
