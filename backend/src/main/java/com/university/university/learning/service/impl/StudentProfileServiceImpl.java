package com.university.university.learning.service.impl;



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

    /**
     * 保存或更新画像，只覆盖非 null 字段，已有有效值不会被冲掉
     */
    @Override
    public StudentProfile saveOrUpdateProfile(Long userId, StudentProfile incoming) {
        StudentProfile exist = this.getByUserId(userId);

        if (exist != null) {
            // 只合并非 null 字段，保留 DB 中已有的有效值
            if (incoming.getKnowledgeBase() != null) exist.setKnowledgeBase(incoming.getKnowledgeBase());
            if (incoming.getCognitiveStyle() != null) exist.setCognitiveStyle(incoming.getCognitiveStyle());
            if (incoming.getLearningGoal() != null) exist.setLearningGoal(incoming.getLearningGoal());
            if (incoming.getWeakPoints() != null) exist.setWeakPoints(incoming.getWeakPoints());
            if (incoming.getLearningPace() != null) exist.setLearningPace(incoming.getLearningPace());
            if (incoming.getInterestDirection() != null) exist.setInterestDirection(incoming.getInterestDirection());
            if (incoming.getRawProfileJson() != null) exist.setRawProfileJson(incoming.getRawProfileJson());
            exist.setUpdatedAt(LocalDateTime.now());
            this.updateById(exist);
            log.info("更新画像: userId={}", userId);
            return exist;
        } else {
            incoming.setUserId(userId);
            this.save(incoming);
            log.info("创建画像: userId={}", userId);
            return incoming;
        }
    }
}