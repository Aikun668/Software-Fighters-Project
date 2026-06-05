package com.university.learning.utils;

import cn.hutool.core.bean.BeanUtil;
import cn.hutool.core.util.StrUtil;
import com.university.learning.dto.UserDTO;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.web.servlet.HandlerInterceptor;

import java.util.Map;
import java.util.concurrent.TimeUnit;

import static com.university.learning.utils.RedisConstants.LOGIN_USER_KEY;
import static com.university.learning.utils.RedisConstants.LOGIN_USER_TTL;

public class RefreshTokenInterceptor  implements HandlerInterceptor {

    private final StringRedisTemplate stringRedisTemplate;

    public RefreshTokenInterceptor(StringRedisTemplate stringRedisTemplate) {
        this.stringRedisTemplate = stringRedisTemplate;
    }
    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) throws Exception {
        // 1. 获取请求头中的token
        String token = request.getHeader("authorization");

        if (StrUtil.isBlank(token)){
            return true;
        }

        //并处理 Bearer 前缀
        if (token.startsWith("Bearer ")) {
            token = token.substring(7);  // 去掉 "Bearer "
        }
        System.out.println("===== token: " + token);
        String tokenKey=LOGIN_USER_KEY+token;
        String uri = request.getRequestURI();

        if (uri.contains("swagger") ||
                uri.contains("api-docs") ||
                uri.contains("webjars") ||
                uri.startsWith("/swagger-ui") ||
                uri.endsWith(".html") ||
                uri.endsWith(".css") ||
                uri.endsWith(".js") ||
                uri.endsWith(".png") ||
                uri.endsWith(".ico") ||
                uri.endsWith(".json")) {
            return true;
        }



        //2. 基于Token获取redis中的用户
        Map<Object,Object> userMap =stringRedisTemplate.opsForHash().entries(tokenKey);

        //3.判断用户是否存在
        if (userMap.isEmpty()){
            //4.不存在，放行
            return true;
        }

        UserDTO userdTO = BeanUtil.fillBeanWithMap(userMap, new UserDTO(), false);

        //5.存在，保存用户信息到ThreadLocal
        UserHolder.saveUser(userdTO);

        //7.刷新token有效期
        stringRedisTemplate.expire(tokenKey,LOGIN_USER_TTL, TimeUnit.MINUTES);
        //6放行
        return true;
    }

    @Override
    public void afterCompletion(HttpServletRequest request, HttpServletResponse response, Object handler, Exception ex) throws Exception {
        UserHolder.removeUser();
    }
}
