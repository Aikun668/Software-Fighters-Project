package com.university.learning.utils;


import com.university.learning.dto.UserDTO;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
public class LoginInterceptor  implements HandlerInterceptor {

    @Value("${learning.auth.required:true}")
    private boolean authRequired;

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) throws Exception {
        if (!authRequired) {
            UserDTO dev = new UserDTO();
            dev.setId(1L);
            dev.setUsername("dev_user");
            dev.setAvatarUrl(null);
            UserHolder.saveUser(dev);
            return true;
        }

        if (UserHolder.getUser() == null){
            response.setStatus(401);
            response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write("{\"error\":\"请先登录\"}");
            return false;
        }
        return true;
    }

    @Override
    public void afterCompletion(HttpServletRequest request, HttpServletResponse response, Object handler, Exception ex) throws Exception {
        UserHolder.removeUser();
    }
}
