package com.university.learning.controller;

import com.university.learning.common.Result;
import com.university.learning.entity.NodeMastery;
import com.university.learning.service.IKnowledgeGraphService;
import com.university.learning.service.INodeMasteryService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 知识图谱接口 — 纯Java，不调Python
 * 颜色/状态渲染由前端根据 mastery 值自行计算
 */
@Slf4j
@RestController
@RequestMapping("/api/knowledge-graph")
@RequiredArgsConstructor
public class KnowledgeGraphController {

    private final IKnowledgeGraphService graphService;
    private final INodeMasteryService masteryService;

    /**
     * 获取完整知识图谱（节点+边+用户掌握度）
     * GET /api/knowledge-graph/ai_intro?user_id=1
     */
    @GetMapping("/{courseId}")
    public Result getGraph(@PathVariable String courseId, @RequestParam Long userId) {
        Map<String, Float> masteries = buildMasteryMap(userId, courseId);
        Map<String, Object> graph = graphService.getGraph(courseId, masteries);
        return Result.ok(graph);
    }

    /**
     * 获取节点卡片详情
     * GET /api/knowledge-graph/{courseId}/nodes/{nodeId}?user_id=1
     */
    @GetMapping("/{courseId}/nodes/{nodeId}")
    public Result getNodeCard(@PathVariable String courseId,
                              @PathVariable String nodeId,
                              @RequestParam Long userId,
                              @RequestParam(defaultValue = "0") int totalExercises,
                              @RequestParam(required = false) String lastPracticed) {
        Map<String, Float> masteries = buildMasteryMap(userId, courseId);
        Map<String, Object> card = graphService.getNodeCard(
                courseId, nodeId, masteries, totalExercises, lastPracticed);
        if (card == null) {
            return Result.fail(404, "节点不存在");
        }
        return Result.ok(card);
    }

    /**
     * 获取用户掌握度（纯查库）
     * GET /api/knowledge-graph/masteries/{courseId}?user_id=1
     */
    @GetMapping("/masteries/{courseId}")
    public Result getMasteries(@PathVariable String courseId, @RequestParam Long userId) {
        Map<String, Float> map = buildMasteryMap(userId, courseId);
        Map<String, Object> distribution = masteryService.getDistribution(userId, courseId);
        Map<String, Object> result = new HashMap<>();
        result.put("masteries", map);
        result.put("distribution", distribution);
        return Result.ok(result);
    }

    private Map<String, Float> buildMasteryMap(Long userId, String courseId) {
        List<NodeMastery> list = masteryService.listByUserIdAndCourseId(userId, courseId);
        Map<String, Float> map = new HashMap<>();
        for (NodeMastery nm : list) {
            map.put(nm.getNodeId(), nm.getMastery() != null ? nm.getMastery() : 0f);
        }
        return map;
    }
}
