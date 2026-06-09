package com.university.learning.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class RegisterFormDTO {
    private String phone;
    private String code;
    private String password;
    private String passwordConfirm;
    private String username;

}
