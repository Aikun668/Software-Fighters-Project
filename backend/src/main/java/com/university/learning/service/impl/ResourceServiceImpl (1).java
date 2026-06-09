package com.university.learning.service.impl;


import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.university.learning.entity.Resource;
import com.university.learning.mapper.ResourceMapper;
import com.university.learning.service.IResourceService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Slf4j
@Service
public class ResourceServiceImpl extends ServiceImpl<ResourceMapper, Resource> implements IResourceService {

    @Override
    public List<Resource> listByUserId(Long userId) {
        return this.list(
                new LambdaQueryWrapper<Resource>()
                        .eq(Resource::getUserId, userId)
                        .orderByDesc(Resource::getCreatedAt)
        );
    }

    @Override
    public List<Resource> listByType(Long userId, String type) {
        return this.list(
                new LambdaQueryWrapper<Resource>()
                        .eq(Resource::getUserId, userId)
                        .eq(Resource::getType, type)
                        .orderByDesc(Resource::getCreatedAt)
        );
    }

    @Override
    public Resource getResourceDetail(Long resourceId) {
        Resource resource = this.getById(resourceId);
        if (resource == null) {
            throw new RuntimeException("资源不存在");
        }
        return resource;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public boolean saveBatch2(List<Resource> resources) {
        try {
            return this.saveBatch(resources);
        } catch (Exception e) {
            log.error("批量保存资源失败", e);
            throw new RuntimeException("批量保存资源失败: " + e.getMessage());
        }
    }
}