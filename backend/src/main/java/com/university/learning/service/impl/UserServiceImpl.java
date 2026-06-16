package com.university.learning.service.impl;

import cn.hutool.captcha.CaptchaUtil;
import cn.hutool.captcha.LineCaptcha;
import cn.hutool.core.bean.BeanUtil;
import cn.hutool.core.lang.UUID;
import cn.hutool.core.util.StrUtil;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.university.learning.common.Result;
import com.university.learning.dto.LoginFormDTO;
import com.university.learning.dto.RegisterFormDTO;
import com.university.learning.dto.UserDTO;
import com.university.learning.entity.User;
import com.university.learning.mapper.UserMapper;
import com.university.learning.service.IUserService;
import jakarta.annotation.Resource;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import static com.university.learning.utils.RedisConstants.*;

@Service
public class UserServiceImpl extends ServiceImpl<UserMapper, User> implements IUserService {

    @Resource
    private BCryptPasswordEncoder passwordEncoder;

    @Resource
    private StringRedisTemplate stringRedisTemplate;

    @Override
    public Result generateCaptcha() {
        LineCaptcha captcha = CaptchaUtil.createLineCaptcha(200, 100, 4, 20);
        String code = captcha.getCode();
        String key = UUID.randomUUID().toString(true);

        stringRedisTemplate.opsForValue().set(CAPTCHA_KEY + key, code, CAPTCHA_TTL, TimeUnit.MINUTES);

        Map<String, String> data = new HashMap<>();
        data.put("captchaKey", key);
        data.put("captchaImage", captcha.getImageBase64Data());
        return Result.ok(data);
    }

    @Override
    public Result login(LoginFormDTO loginForm) {
        String username = loginForm.getUsername();
        String password = loginForm.getPassword();

        if (StrUtil.isBlank(username)) {
            return Result.fail("用户名不能为空");
        }
        if (StrUtil.isBlank(password)) {
            return Result.fail("密码不能为空");
        }

        User user = query().eq("username", username).one();
        if (user == null) {
            return Result.fail("用户不存在，请先注册");
        }

        if (!passwordEncoder.matches(password, user.getPassword())) {
            return Result.fail("密码错误");
        }

        String token = UUID.randomUUID().toString(true);
        String tokenKey = LOGIN_USER_KEY + token;
        UserDTO userDTO = BeanUtil.copyProperties(user, UserDTO.class);

        Map<String, Object> userMap = new HashMap<>();
        userMap.put("id", userDTO.getId().toString());
        userMap.put("username", userDTO.getUsername());
        userMap.put("avatarUrl", userDTO.getAvatarUrl());

        stringRedisTemplate.opsForHash().putAll(tokenKey, userMap);
        stringRedisTemplate.expire(tokenKey, LOGIN_USER_TTL, TimeUnit.MINUTES);

        // 返回 token + 用户信息
        Map<String, Object> loginResult = new HashMap<>();
        loginResult.put("token", token);
        Map<String, Object> userInfo = new HashMap<>();
        userInfo.put("id", user.getId());
        userInfo.put("username", user.getUsername());
        userInfo.put("avatarUrl", user.getAvatarUrl());
        userInfo.put("role", user.getRole());
        loginResult.put("userInfo", userInfo);
        return Result.ok(loginResult);
    }

    @Override
    public Result register(RegisterFormDTO registerForm) {
        String username = registerForm.getUsername();
        String password = registerForm.getPassword();
        String passwordConfirm = registerForm.getPasswordConfirm();

        if (StrUtil.isBlank(username)) {
            return Result.fail("用户名不能为空");
        }
        if (username.length() < 2 || username.length() > 20) {
            return Result.fail("用户名长度需在2-20位之间");
        }

        User exist = query().eq("username", username).one();
        if (exist != null) {
            return Result.fail("用户名已存在");
        }

        if (StrUtil.isBlank(password) || password.length() < 6) {
            return Result.fail("密码长度至少6位");
        }
        if (!password.equals(passwordConfirm)) {
            return Result.fail("两次输入的密码不一致");
        }

        // 校验图片验证码
        String captchaKey = registerForm.getCaptchaKey();
        String captchaCode = registerForm.getCaptchaCode();
        if (StrUtil.isBlank(captchaKey) || StrUtil.isBlank(captchaCode)) {
            return Result.fail("请输入验证码");
        }
        String cachedCode = stringRedisTemplate.opsForValue().get(CAPTCHA_KEY + captchaKey);
        if (cachedCode == null) {
            return Result.fail("验证码已过期，请重新获取");
        }
        if (!captchaCode.equalsIgnoreCase(cachedCode)) {
            return Result.fail("验证码错误");
        }
        stringRedisTemplate.delete(CAPTCHA_KEY + captchaKey);

        User user = new User()
                .setUsername(username)
                .setPassword(passwordEncoder.encode(password))
                .setStatus(1)
                .setCreatedAt(LocalDateTime.now())
                .setUpdatedAt(LocalDateTime.now());

        save(user);
        return Result.ok("注册成功");
    }
}
