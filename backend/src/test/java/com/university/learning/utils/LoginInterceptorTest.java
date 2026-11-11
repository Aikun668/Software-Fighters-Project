package com.university.learning.utils;

import com.university.learning.dto.UserDTO;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.io.PrintWriter;
import java.io.StringWriter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class LoginInterceptorTest {

    @AfterEach
    void clearUser() {
        UserHolder.removeUser();
    }

    @Test
    void authOffDoesNotOverwriteAnAlreadyResolvedUser() throws Exception {
        LoginInterceptor interceptor = interceptor(false);
        UserDTO existing = new UserDTO();
        existing.setId(7L);
        existing.setUsername("real_user");
        UserHolder.saveUser(existing);

        assertTrue(interceptor.preHandle(mock(HttpServletRequest.class), mock(HttpServletResponse.class), new Object()));
        assertEquals(7L, UserHolder.getUser().getId());
        assertEquals("real_user", UserHolder.getUser().getUsername());
    }

    @Test
    void authOffFallsBackToDevUserOnlyWhenNobodyIsResolved() throws Exception {
        LoginInterceptor interceptor = interceptor(false);
        assertTrue(interceptor.preHandle(mock(HttpServletRequest.class), mock(HttpServletResponse.class), new Object()));
        assertEquals(1L, UserHolder.getUser().getId());
    }

    @Test
    void authOnRejectsAnonymousRequests() throws Exception {
        LoginInterceptor interceptor = interceptor(true);
        HttpServletResponse response = mock(HttpServletResponse.class);
        when(response.getWriter()).thenReturn(new PrintWriter(new StringWriter()));

        assertFalse(interceptor.preHandle(mock(HttpServletRequest.class), response, new Object()));
        verify(response).setStatus(401);
    }

    private static LoginInterceptor interceptor(boolean required) {
        LoginInterceptor interceptor = new LoginInterceptor();
        ReflectionTestUtils.setField(interceptor, "authRequired", required);
        return interceptor;
    }
}
