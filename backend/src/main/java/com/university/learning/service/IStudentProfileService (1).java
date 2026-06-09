package com.university.learning.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.university.learning.entity.StudentProfile;

public interface IStudentProfileService extends IService<StudentProfile> {

    /**
     * 获取学生画像
     */
    StudentProfile getByUserId(Long userId);

    /**
     * 创建或更新画像
     */
    StudentProfile saveOrUpdateProfile(Long userId, StudentProfile profile);
}