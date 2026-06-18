package com.university.university.learning.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.university.learning.common.Result;
import com.university.learning.dto.LoginFormDTO;
import com.university.learning.dto.RegisterFormDTO;
import com.university.learning.entity.User;

public interface IUserService extends IService<User> {

    Result generateCaptcha();

    Result login(LoginFormDTO loginForm);

    Result register(RegisterFormDTO registerForm);
}
