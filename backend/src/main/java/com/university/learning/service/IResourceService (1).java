package com.university.learning.service;


import com.baomidou.mybatisplus.extension.service.IService;
import com.university.learning.entity.Resource;

import java.util.List;

public interface IResourceService extends IService<Resource> {

    /**
     * 根据用户ID查询资源列表
     */
    List<Resource> listByUserId(Long userId);

    /**
     * 根据类型查询资源
     */
    List<Resource> listByType(Long userId, String type);

    /**
     * 获取资源详情
     */
    Resource getResourceDetail(Long resourceId);

    /**
     * 批量保存资源
     */
    boolean saveBatch2(List<Resource> resources);
}