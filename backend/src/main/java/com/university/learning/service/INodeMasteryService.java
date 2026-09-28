package com.university.learning.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.university.learning.entity.NodeMastery;

import java.util.List;
import java.util.Map;

/**
 * 节点掌握度服务接口
 */
public interface INodeMasteryService extends IService<NodeMastery> {

    /** 获取用户在指定课程的所有节点掌握度 */
    List<NodeMastery> listByUserIdAndCourseId(Long userId, String courseId);

    /** 获取单个节点的掌握度详情 */
    NodeMastery getByUserIdAndNodeId(Long userId, String nodeId);

    /** 写入/更新节点掌握度（upsert语义） */
    NodeMastery upsert(Long userId, String nodeId, String courseId, Float mastery, Integer reviewCount);

    /**
     * 将 Python 返回的 mastery_updates 落库为最终掌握度。
     *
     * @param masteryUpdates {node_id: {new_mastery: Float, ...}}，old_mastery/delta 仅作参考，不写入
     * @return 实际写入的节点数
     */
    int applyMasteryUpdates(Long userId, String courseId, Map<String, Object> masteryUpdates);

    /** 获取掌握度分布统计 */
    Map<String, Object> getDistribution(Long userId, String courseId);
}
