package com.university.learning.controller;

import com.university.learning.common.Result;
import com.university.learning.dto.LoginFormDTO;
import com.university.learning.dto.RegisterFormDTO;
import com.university.learning.service.IUserService;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.annotation.Resource;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/user")
public class UserController {

    @Resource
    private IUserService userService;

    @Operation(summary = "获取图片验证码", description = "生成图形验证码图片，返回 captchaKey 和 base64 图片")
    @GetMapping("/captcha")
    public Result captcha() {
        return userService.generateCaptcha();
    }

    @Operation(summary = "用户注册", description = "用户名 + 密码 + 图片验证码注册，用户名2-20位，密码至少6位")
    @PostMapping("/register")
    public Result register(@RequestBody RegisterFormDTO registerForm) {
        return userService.register(registerForm);
    }

    @Operation(summary = "用户登录", description = "用户名 + 密码登录，返回 token + 用户信息，同时设置 authorization 响应头")
    @PostMapping("/login")
    @SuppressWarnings("unchecked")
    public Result login(@RequestBody LoginFormDTO loginForm, HttpServletResponse response) {
        Result result = userService.login(loginForm);
        if (result.getData() instanceof Map) {
            Map<String, Object> data = (Map<String, Object>) result.getData();
            Object token = data.get("token");
            if (token != null) {
                response.setHeader("authorization", token.toString());
            }
        }
        return result;
    }
}
