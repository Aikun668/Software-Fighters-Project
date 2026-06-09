package com.university.learning.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.university.learning.entity.NodeMastery;
import com.university.learning.mapper.NodeMasteryMapper;
import com.university.learning.service.INodeMasteryService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 节点掌握度服务实现
 */
@Service
public class NodeMasteryServiceImpl extends ServiceImpl<NodeMasteryMapper, NodeMastery> implements INodeMasteryService {

    @Override
    public List<NodeMastery> listByUserIdAndCourseId(Long userId, String courseId) {
        return this.list(
                new LambdaQueryWrapper<NodeMastery>()
                        .eq(NodeMastery::getUserId, userId)
                        .eq(NodeMastery::getCourseId, courseId)
        );
    }

    @Override
    public NodeMastery getByUserIdAndNodeId(Long userId, String nodeId) {
        return this.getOne(
                new LambdaQueryWrapper<NodeMastery>()
                        .eq(NodeMastery::getUserId, userId)
                        .eq(NodeMastery::getNodeId, nodeId)
        );
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public NodeMastery upsert(Long userId, String nodeId, String courseId, Float mastery, Integer reviewCount) {
        // 查找已存在的记录
        NodeMastery existing = this.getOne(
                new LambdaQueryWrapper<NodeMastery>()
                        .eq(NodeMastery::getUserId, userId)
                        .eq(NodeMastery::getNodeId, nodeId)
        );

        if (existing != null) {
            // 更新已有记录
            existing.setMastery(mastery);
            existing.setReviewCount(reviewCount);
            existing.setLastReviewAt(LocalDateTime.now());
            this.updateById(existing);
            return existing;
        }

        // 插入新记录
        NodeMastery nm = new NodeMastery()
                .setUserId(userId)
                .setNodeId(nodeId)
                .setCourseId(courseId)
                .setMastery(mastery)
                .setReviewCount(reviewCount)
                .setLastReviewAt(LocalDateTime.now());
        this.save(nm);
        return nm;
    }

    @Override
    public Map<String, Object> getDistribution(Long userId, String courseId) {
        List<NodeMastery> list = this.listByUserIdAndCourseId(userId, courseId);

        int mastered = 0, inProgress = 0, weak = 0;
        float totalMastery = 0;

        // mastery >= 0.8 → mastered, >= 0.4 → in_progress, < 0.4 → weak
        for (NodeMastery nm : list) {
            float m = nm.getMastery() != null ? nm.getMastery() : 0;
            totalMastery += m;
            if (m >= 0.8f) mastered++;
            else if (m >= 0.4f) inProgress++;
            else weak++;
        }

        Map<String, Object> dist = new HashMap<>();
        dist.put("mastered", mastered);
        dist.put("in_progress", inProgress);
        dist.put("weak", weak);
        dist.put("overall_pct", list.isEmpty() ? 0 : totalMastery / list.size());
        return dist;
    }
}
