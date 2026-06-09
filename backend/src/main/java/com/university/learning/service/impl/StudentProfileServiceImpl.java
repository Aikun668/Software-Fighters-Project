package com.university.learning.service.impl;



import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.university.learning.entity.StudentProfile;
import com.university.learning.mapper.StudentProfileMapper;
import com.university.learning.service.IStudentProfileService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;

@Slf4j
@Service
public class StudentProfileServiceImpl extends ServiceImpl<StudentProfileMapper, StudentProfile> implements IStudentProfileService {

    @Override
    public StudentProfile getByUserId(Long userId) {
        return this.getOne(
                new LambdaQueryWrapper<StudentProfile>()
                        .eq(StudentProfile::getUserId, userId)
        );
    }

    @Override
    public StudentProfile saveOrUpdateProfile(Long userId, StudentProfile profile) {
        StudentProfile existProfile = this.getByUserId(userId);

        if (existProfile != null) {
            profile.setId(existProfile.getId());
            profile.setUserId(userId);
            profile.setUpdatedAt(LocalDateTime.now());
            this.updateById(profile);
            log.info("更新画像: userId={}", userId);
            return profile;
        } else {
            profile.setUserId(userId);
            this.save(profile);
            log.info("创建画像: userId={}", userId);
            return profile;
        }
    }
}