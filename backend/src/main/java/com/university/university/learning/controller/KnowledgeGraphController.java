package com.university.university.learning.controller;

import com.university.learning.common.Result;
import com.university.learning.service.IKnowledgeGraphService;
import com.university.learning.service.INodeMasteryService;
import io.swagger.v3.oas.annotations.Operation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/knowledge-graph")
@RequiredArgsConstructor
public class KnowledgeGraphController {

    private final IKnowledgeGraphService graphService;
    private final INodeMasteryService masteryService;

    @Operation(summary = "获取课程知识图谱", description = "返回节点+边+用户掌握度，courseId 如 ai_intro")
    @GetMapping("/{courseId}")
    public Result getGraph(@PathVariable String courseId, @RequestParam Long userId) {
        Map<String, Float> masteries = buildMasteryMap(userId, courseId);
        Map<String, Object> graph = graphService.getGraph(courseId, masteries);
        return Result.ok(graph);
    }

    @Operation(summary = "获取节点详情卡片", description = "返回节点信息、前置/后置依赖关系、学习表现")
    @GetMapping("/{courseId}/node/{nodeId}")
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

    @Operation(summary = "获取用户掌握度分布", description = "返回各节点掌握度 map + 整体分布统计")
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
        return masteryService.buildMasteryMap(userId, courseId);
    }
}
