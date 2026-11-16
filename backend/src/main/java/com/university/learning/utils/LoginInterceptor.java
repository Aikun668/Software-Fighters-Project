package com.university.learning.utils;


import com.university.learning.dto.UserDTO;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
public class LoginInterceptor  implements HandlerInterceptor {

    /**
     * Still bound from {@code learning.auth.required}. Neither value installs a shared
     * dev user. A request continues only when a login token was already resolved.
     */
    @Value("${learning.auth.required:true}")
    private boolean authRequired;

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) throws Exception {
        UserDTO current = UserHolder.getUser();
        if (current != null && current.getId() != null) {
            return true;
        }
        // authRequired is intentionally not a bypass. false used to stamp every
        // unresolved session as user id 1, which shared maps, chat sentences,
        // accept/reject decisions and adaptive plans. Both settings refuse here.
        if (!authRequired) {
            reject(response);
            return false;
        }
        reject(response);
        return false;
    }

    private static void reject(HttpServletResponse response) throws Exception {
        response.setStatus(401);
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write("{\"error\":\"请先登录\"}");
    }

    @Override
    public void afterCompletion(HttpServletRequest request, HttpServletResponse response, Object handler, Exception ex) throws Exception {
        UserHolder.removeUser();
    }
}
