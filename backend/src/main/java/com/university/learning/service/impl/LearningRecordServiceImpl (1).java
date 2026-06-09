package com.university.learning.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.university.learning.entity.LearningRecord;
import com.university.learning.entity.Resource;
import com.university.learning.mapper.LearningRecordMapper;
import com.university.learning.mapper.ResourceMapper;
import com.university.learning.service.ILearningRecordService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
public class LearningRecordServiceImpl extends ServiceImpl<LearningRecordMapper, LearningRecord> implements ILearningRecordService {

    private final ResourceMapper resourceMapper;

    @Override
    public LearningRecord saveOrUpdateProgress(LearningRecord record) {
        LearningRecord existRecord = this.getByUserAndResource(record.getUserId(), record.getResourceId());

        if (existRecord != null) {
            record.setId(existRecord.getId());
            this.updateById(record);
            log.info("更新学习进度: userId={}, resourceId={}, progress={}, score={}",
                    record.getUserId(), record.getResourceId(), record.getProgress(), record.getScore());
        } else {
            this.save(record);
            log.info("创建学习记录: userId={}, resourceId={}, progress={}, score={}",
                    record.getUserId(), record.getResourceId(), record.getProgress(), record.getScore());
        }

        return record;
    }

    @Override
    public List<LearningRecord> listByUserId(Long userId) {
        return this.list(
                new LambdaQueryWrapper<LearningRecord>()
                        .eq(LearningRecord::getUserId, userId)
                        .orderByDesc(LearningRecord::getCreatedAt)
        );
    }

    @Override
    public LearningRecord getByUserAndResource(Long userId, Long resourceId) {
        return this.getOne(
                new LambdaQueryWrapper<LearningRecord>()
                        .eq(LearningRecord::getUserId, userId)
                        .eq(LearningRecord::getResourceId, resourceId)
        );
    }

    @Override
    public List<LearningRecord> listByUserIdAndType(Long userId, String resourceType) {
        // 先查出该类型的所有资源ID
        List<Long> resourceIds = resourceMapper.selectList(
                new LambdaQueryWrapper<Resource>()
                        .eq(Resource::getUserId, userId)
                        .eq(Resource::getType, resourceType)
        ).stream().map(Resource::getId).toList();

        if (resourceIds.isEmpty()) {
            return List.of();
        }

        return this.list(
                new LambdaQueryWrapper<LearningRecord>()
                        .eq(LearningRecord::getUserId, userId)
                        .in(LearningRecord::getResourceId, resourceIds)
                        .orderByDesc(LearningRecord::getCreatedAt)
        );
    }

    @Override
    public Float getTotalScore(Long userId) {
        List<LearningRecord> records = this.listByUserId(userId);
        return records.stream()
                .map(LearningRecord::getScore)
                .filter(score -> score != null)
                .reduce(0f, Float::sum);
    }

    @Override
    public Float getAverageScore(Long userId) {
        List<LearningRecord> records = this.listByUserId(userId);
        return (float) records.stream()
                .map(LearningRecord::getScore)
                .filter(score -> score != null)
                .mapToDouble(Float::doubleValue)
                .average()
                .orElse(0);
    }
}