package com.university.learning.controller;

import com.university.learning.common.Result;
import com.university.learning.entity.NodeMastery;
import com.university.learning.service.INodeMasteryService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/**
 * 节点掌握度接口
 */
@RestController
@RequestMapping("/api/node-masteries")
@RequiredArgsConstructor
public class NodeMasteryController {

    private final INodeMasteryService masteryService;

    /** 获取用户在指定课程的所有节点掌握度 */
    @GetMapping
    public Result list(@RequestParam Long userId, @RequestParam String courseId) {
        List<NodeMastery> list = masteryService.listByUserIdAndCourseId(userId, courseId);
        return Result.ok(list);
    }

    /** 获取单个节点的掌握度详情 */
    @GetMapping("/{nodeId}")
    public Result getDetail(@PathVariable String nodeId, @RequestParam Long userId) {
        NodeMastery mastery = masteryService.getByUserIdAndNodeId(userId, nodeId);
        if (mastery == null) {
            return Result.fail(404, "掌握度记录不存在");
        }
        return Result.ok(mastery);
    }

    /** 写入/更新节点掌握度（upsert语义） */
    @PutMapping("/{nodeId}")
    public Result upsert(@PathVariable String nodeId, @RequestBody Map<String, Object> body) {
        Long userId = Long.valueOf(body.get("user_id").toString());
        String courseId = (String) body.get("course_id");
        Float mastery = body.get("mastery") != null ? Float.valueOf(body.get("mastery").toString()) : 0f;
        Integer reviewCount = body.get("review_count") != null ? toInt(body.get("review_count")) : 1;

        NodeMastery result = masteryService.upsert(userId, nodeId, courseId, mastery, reviewCount);
        return Result.ok(result);
    }

    /** 获取掌握度分布统计 */
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
