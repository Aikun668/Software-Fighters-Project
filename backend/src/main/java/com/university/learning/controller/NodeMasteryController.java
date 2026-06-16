package com.university.learning.controller;

import com.university.learning.common.Result;
import com.university.learning.entity.NodeMastery;
import com.university.learning.service.INodeMasteryService;
import io.swagger.v3.oas.annotations.Operation;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/node-masteries")
@RequiredArgsConstructor
public class NodeMasteryController {

    private final INodeMasteryService masteryService;

    @Operation(summary = "获取课程所有节点掌握度", description = "查询用户在指定课程下所有知识节点的掌握度")
    @GetMapping
    public Result list(@RequestParam Long userId, @RequestParam String courseId) {
        List<NodeMastery> list = masteryService.listByUserIdAndCourseId(userId, courseId);
        return Result.ok(list);
    }

    @Operation(summary = "获取单个节点掌握度")
    @GetMapping("/{nodeId}")
    public Result getDetail(@PathVariable String nodeId, @RequestParam Long userId) {
        NodeMastery mastery = masteryService.getByUserIdAndNodeId(userId, nodeId);
        if (mastery == null) {
            return Result.fail(404, "掌握度记录不存在");
        }
        return Result.ok(mastery);
    }

    @Operation(summary = "写入/更新节点掌握度", description = "upsert 语义：存在则更新，不存在则创建")
    @PutMapping("/{nodeId}")
    public Result upsert(@PathVariable String nodeId, @RequestBody Map<String, Object> body) {
        Long userId = Long.valueOf(body.get("user_id").toString());
        String courseId = (String) body.get("course_id");
        Float mastery = body.get("mastery") != null ? Float.valueOf(body.get("mastery").toString()) : 0f;
        Integer reviewCount = body.get("review_count") != null ? toInt(body.get("review_count")) : 1;

        NodeMastery result = masteryService.upsert(userId, nodeId, courseId, mastery, reviewCount);
        return Result.ok(result);
    }

    @Operation(summary = "获取掌握度分布统计", description = "按掌握度等级(0-0.2/0.2-0.4/...)分布统计")
    @GetMapping("/distribution")
    public Result getDistribution(@RequestParam Long userId, @RequestParam String courseId) {
        Map<String, Object> dist = masteryService.getDistribution(userId, courseId);
        return Result.ok(dist);
    }

    private int toInt(Object value) {
        if (value instanceof Number) return ((Number) value).intValue();
        return Integer.parseInt(value.toString());
    }
}
