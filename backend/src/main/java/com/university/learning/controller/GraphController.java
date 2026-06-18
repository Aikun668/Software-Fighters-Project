package com.university.learning.controller;

import com.university.learning.client.PythonClient;
import com.university.learning.common.Result;
import com.university.learning.dto.*;
import com.university.learning.entity.NodeMastery;
import com.university.learning.service.INodeMasteryService;
import com.university.learning.utils.UserHolder;
import io.swagger.v3.oas.annotations.Operation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 知识图谱分析/维护/可视化控制器。
 * 所有接口 POST 方式，Java 从数据库读取数据后传入 Python 做 AI 计算。
 */
@Slf4j
@RestController
@RequestMapping("/api/graph")
@RequiredArgsConstructor
public class GraphController {

    private final PythonClient pythonClient;
    private final INodeMasteryService masteryService;

    /** 从对话内容中提取知识节点 */
    @Operation(summary = "提取知识节点", description = "从用户消息和AI回复中提取主节点+关联节点+候选节点")
    @PostMapping("/extract")
    public Result extractNodes(@RequestBody GraphExtractRequest request) {
        try {
            String courseId = request.getCourse_id() != null ? request.getCourse_id() : "ai_intro";
            Map<String, Object> result = pythonClient.extractGraphNodes(
                    courseId, request.getUser_message(), request.getAssistant_reply(),
                    request.getExisting_node_ids());
            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /** 批量更新图谱节点和边 */
    @Operation(summary = "更新图谱节点/边", description = "批量 add_node / add_edge 操作")
    @PostMapping("/nodes")
    public Result updateNodes(@RequestBody GraphNodesRequest request) {
        try {
            String courseId = request.getCourse_id() != null ? request.getCourse_id() : "ai_intro";
            Map<String, Object> result = pythonClient.updateGraphNodes(courseId, request.getUpdates());
            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /** 根据学习事件批量更新节点掌握度 */
    @Operation(summary = "更新节点掌握度", description = "根据学习事件批量计算掌握度变化，Java自行持久化")
    @PostMapping("/masteries")
    public Result updateMasteries(@RequestBody MasteryUpdateRequest request) {
        try {
            Long userId = UserHolder.getUser().getId();
            String courseId = request.getCourse_id() != null ? request.getCourse_id() : "ai_intro";
            Map<String, Float> masteries = buildMasteryMap(userId, courseId);
            Map<String, Object> result = pythonClient.updateMasteries(courseId, masteries, request.getEvents());
            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /** 推荐下一个该学的节点 */
    @Operation(summary = "推荐下一节点", description = "根据当前掌握度进行知识缺口分析，推荐下一个该学的节点")
    @PostMapping("/next-node")
    public Result nextNode(@RequestBody GraphRequest request) {
        try {
            Long userId = UserHolder.getUser().getId();
            String courseId = request.getCourse_id() != null ? request.getCourse_id() : "ai_intro";
            Map<String, Float> masteries = buildMasteryMap(userId, courseId);
            Map<String, Object> result = pythonClient.recommendNextNode(masteries, courseId);
            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /** 学习进度概要 */
    @Operation(summary = "学习进度概要", description = "全局掌握率 + 各分类统计")
    @PostMapping("/progress")
    public Result progress(@RequestBody GraphRequest request) {
        try {
            Long userId = UserHolder.getUser().getId();
            String courseId = request.getCourse_id() != null ? request.getCourse_id() : "ai_intro";
            Map<String, Float> masteries = buildMasteryMap(userId, courseId);
            Map<String, Object> result = pythonClient.getGraphProgress(masteries, courseId);
            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /** 前置条件检查 */
    @Operation(summary = "前置条件检查", description = "检查用户是否可以学习指定节点")
    @PostMapping("/check-prerequisites")
    public Result checkPrerequisites(@RequestBody GraphRequest request) {
        try {
            Long userId = UserHolder.getUser().getId();
            String courseId = request.getCourse_id() != null ? request.getCourse_id() : "ai_intro";
            String nodeId = request.getNode_id();
            double threshold = request.getThreshold() != null ? request.getThreshold() : 0.6;
            Map<String, Float> masteries = buildMasteryMap(userId, courseId);
            Map<String, Object> result = pythonClient.checkPrerequisites(
                    nodeId, masteries, threshold, courseId);
            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /** 导出 Mermaid 流程图 */
    @Operation(summary = "导出Mermaid", description = "导出知识图谱为Mermaid流程图语法")
    @PostMapping("/export-mermaid")
    public Result exportMermaid(@RequestBody GraphRequest request) {
        try {
            Long userId = UserHolder.getUser().getId();
            String courseId = request.getCourse_id() != null ? request.getCourse_id() : "ai_intro";
            Map<String, Float> masteries = buildMasteryMap(userId, courseId);
            Map<String, Object> result = pythonClient.exportMermaid(courseId, masteries);
            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /** 分层图谱 */
    @Operation(summary = "分层图谱", description = "返回带层级信息的图谱（前端分层布局）")
    @PostMapping("/layered")
    public Result layered(@RequestBody GraphRequest request) {
        try {
            Long userId = UserHolder.getUser().getId();
            String courseId = request.getCourse_id() != null ? request.getCourse_id() : "ai_intro";
            Map<String, Float> masteries = buildMasteryMap(userId, courseId);
            Map<String, Object> result = pythonClient.getLayeredGraph(masteries, courseId);
            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /** 构建用户掌握度映射 */
    private Map<String, Float> buildMasteryMap(Long userId, String courseId) {
        List<NodeMastery> list = masteryService.listByUserIdAndCourseId(userId, courseId);
        Map<String, Float> map = new HashMap<>();
        for (NodeMastery nm : list) {
            map.put(nm.getNodeId(), nm.getMastery() != null ? nm.getMastery() : 0f);
        }
        return map;
    }
}
