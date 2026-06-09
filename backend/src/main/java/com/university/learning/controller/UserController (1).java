package com.university.learning.controller;

import cn.hutool.core.util.StrUtil;
import com.university.learning.common.Result;
import com.university.learning.dto.LoginFormDTO;
import com.university.learning.dto.RegisterFormDTO;
import com.university.learning.service.IUserService;
import jakarta.annotation.Resource;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/user")
public class UserController {

    @Resource
    private IUserService userService;

    @GetMapping("code")
    public Result sendCode(@RequestParam("phone") String phone, @RequestParam("type") String type) {
        // 发送短信验证码并保存验证码
        return userService.sendCode(phone,type);

    }


    @PostMapping("register")
    public Result register(@RequestBody RegisterFormDTO registerForm) {
        //  实现注册功能
        return userService.register(registerForm);
    }

    @PostMapping("login")
    public Result login(@RequestBody LoginFormDTO loginForm, HttpServletResponse response) {
        //  实现登录功能
        String password = loginForm.getPassword();

        Result result = null;
        if (StrUtil.isBlank(password)) {
            //使用验证码登录
            result = userService.loginByCode(loginForm);
        }
        else {
            //使用密码登录
            result = userService.loginByPassword(loginForm);
            return result;
        }


        // 将token放入响应头
        if (result != null && result.getData() != null) {
            response.setHeader("authorization", result.getData().toString());
        }
        return result;
    }

}