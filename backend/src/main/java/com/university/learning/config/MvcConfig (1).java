package com.university.learning.config;

import com.university.learning.utils.LoginInterceptor;
import com.university.learning.utils.RefreshTokenInterceptor;
import jakarta.annotation.Resource;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcConfig implements WebMvcConfigurer {
    @Resource
    private StringRedisTemplate stringRedisTemplate;

    @Override
    public void addInterceptors(InterceptorRegistry registry){
        //登录拦截器
        registry.addInterceptor(new LoginInterceptor())
                .excludePathPatterns(
                        "/user/login",
                        "/user/code",
                        "/user/register",        // 注册接口
                        "/api/auth/**",      // 认证接口
                        "/api/product/**",
                        "/swagger-ui/**",        // Swagger UI 资源
                        "/v3/api-docs/**",       // Swagger API 文档
                        "/swagger-resources/**", // Swagger 资源
                        "/webjars/**",           // 静态资源
                        "/doc.html",             // Knife4j 文档（如果有）
                        "/error",
                        "/swagger-resources/**",
                        "/webjars/**",
                        "/favicon.ico",
                        "/error",
                        "/doc.html",           // knife4j 可能用到
                        "/swagger-ui.html",    // 传统路径
                        "/v3/api-docs",        // API 文档
                        "/v3/api-docs/swagger-config"
                ).order(1);
        //刷新token拦截器
        registry.addInterceptor(new RefreshTokenInterceptor(stringRedisTemplate))
                .addPathPatterns("/**").order(0);

    }
}
