package com.university.learning.service.impl;

import cn.hutool.core.bean.BeanUtil;
import cn.hutool.core.lang.UUID;
import cn.hutool.core.util.RandomUtil;
import cn.hutool.core.util.StrUtil;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.university.learning.common.Result;
import com.university.learning.dto.LoginFormDTO;
import com.university.learning.dto.RegisterFormDTO;
import com.university.learning.dto.UserDTO;
import com.university.learning.entity.User;
import com.university.learning.mapper.UserMapper;
import com.university.learning.service.IUserService;
import com.university.learning.utils.RegexUtils;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import static com.university.learning.utils.RedisConstants.*;

@Service
@Slf4j
public class UserServiceImpl extends ServiceImpl<UserMapper, User> implements IUserService {

    @Resource
    private BCryptPasswordEncoder passwordEncoder;

    @Resource
    private StringRedisTemplate stringRedisTemplate;
    @Override
    public Result sendCode(String phone, String type) {
        if (!(type.equals("login") || type.equals("register"))){
            return Result.fail("参数错误");
        }
        String codeKey = (type.equals("login") ? LOGIN_CODE_KEY : Register_CODE_KEY) + phone;


        // 1. 校验手机号
        if (RegexUtils.isPhoneInvalid(phone)) {
            // 不符合 返回错误
            return Result.fail("手机号格式错误");
        }

        // 2. 符合，生成验证码
        String code = RandomUtil.randomNumbers(6);
        // 3. 保存验证码到 redis
        stringRedisTemplate.opsForValue().set(codeKey, code,LOGIN_CODE_TTL, TimeUnit.MINUTES);
        //5.发送验证码
        log.debug("发送验证码成功,验证码:{}",code);

        return Result.ok();
    }



    @Override
    public Result loginByCode(LoginFormDTO loginForm) {
        //1.校验手机号
        String phone = loginForm.getPhone();
        if (RegexUtils.isPhoneInvalid(phone)){
            //2.如果不符合，返回错误信息
            return Result.fail("手机格式错误");
        }
        String key = LOGIN_CODE_KEY+phone;
        //2.校验验证码
        String cacheCode = stringRedisTemplate.opsForValue().get(key);
        String code = loginForm.getCode();
        if (cacheCode==null ||  ! cacheCode.equals(code)){
            //3.不一致，报错
            return Result.fail("验证码错误");
        }
        stringRedisTemplate.delete(key);

        //4.一致，根据手机号查询用户
        User user=query().eq("phone",phone).one();

        //5.判断用户是否存在
        if (user==null){
            //6.不存在，创建新用户 并保存
            return Result.fail("用户不存在，请先注册");
        }
        //7.保存用户信息到redis
        String token = UUID.randomUUID().toString(true);
        String tokenKey = LOGIN_USER_KEY+token;
        UserDTO userDTO = BeanUtil.copyProperties(user, UserDTO.class);

        Map<String, Object> userMap = new HashMap<>();
        userMap.put("id", userDTO.getId().toString());
        userMap.put("userName", userDTO.getUsername());
        userMap.put("avatar", userDTO.getAvatarUrl());

        stringRedisTemplate.opsForHash().putAll(tokenKey, userMap);
        //设置token有效期
        stringRedisTemplate.expire(tokenKey,LOGIN_USER_TTL,TimeUnit.MINUTES);
        return Result.ok(token);
    }

    @Override
    public Result loginByPassword(LoginFormDTO loginForm) {
        //1.校验手机号
        String phone = loginForm.getPhone();
        if (RegexUtils.isPhoneInvalid(phone)){
            //2.如果不符合，返回错误信息
            return Result.fail("手机格式错误");
        }
        User user=query().eq("phone",phone).one();
        if (user==null){
            //3.不存在，返回错误信息
            return Result.fail("用户不存在，请先注册");
        }
        String truePassword = user.getPassword();
        String password = loginForm.getPassword();

        //2.校验密码
        if (!passwordEncoder.matches(password,truePassword)){
            //3.不一致，返回错误信息
            return Result.fail("密码错误");
        }
        //7.保存用户信息到redis
        String token = UUID.randomUUID().toString(true);
        String tokenKey = LOGIN_USER_KEY+token;
        UserDTO userDTO = BeanUtil.copyProperties(user, UserDTO.class);

        Map<String, Object> userMap = new HashMap<>();
        userMap.put("id", userDTO.getId().toString());
        userMap.put("nickName", userDTO.getUsername());
        userMap.put("icon", userDTO.getAvatarUrl());

        stringRedisTemplate.opsForHash().putAll(tokenKey, userMap);
        //设置token有效期
        stringRedisTemplate.expire(tokenKey,LOGIN_USER_TTL,TimeUnit.MINUTES);
        return Result.ok(token);

    }

    @Override
    public Result register(RegisterFormDTO registerForm) {
        String phone = registerForm.getPhone();
        if (RegexUtils.isPhoneInvalid(phone)){
            return Result.fail("手机格式错误");
        }
        User user=query().eq("phone",phone).one();
        if (user !=null){
            return Result.fail("用户已存在");
        }
        if (StrUtil.isBlank(registerForm.getUsername())){
            return Result.fail("昵称不能为空");
        }

        String password = registerForm.getPassword();
        String passwordConfirm = registerForm.getPasswordConfirm();
        if (!password.equals(passwordConfirm)){
            return Result.fail("密码不一致");
        }
        // 校验验证码
        String key= Register_CODE_KEY+phone;
        String code = stringRedisTemplate.opsForValue().get(key);
        if (code==null || !code.equals(registerForm.getCode())){
            return Result.fail("验证码错误");
        }
        stringRedisTemplate.delete(key);
        user = new User()
                .setUsername(registerForm.getUsername())
                .setPhone(phone)
                .setPassword(passwordEncoder.encode(password))
                .setStatus(1)
                .setCreatedAt(LocalDateTime.now())
                .setUpdatedAt(LocalDateTime.now());

        save(user);

        return Result.ok("注册成功");
    }


}