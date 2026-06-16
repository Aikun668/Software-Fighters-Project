package com.university.learning.dto;

import lombok.Data;

@Data
public class RegisterFormDTO {
    private String username;
    private String password;
    private String passwordConfirm;
    private String captchaKey;
    private String captchaCode;
}
