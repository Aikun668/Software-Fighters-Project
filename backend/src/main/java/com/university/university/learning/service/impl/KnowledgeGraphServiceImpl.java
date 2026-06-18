package com.university.university.learning.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.university.learning.entity.KnowledgeGraphEdge;
import com.university.learning.entity.KnowledgeGraphNode;
import com.university.learning.mapper.KnowledgeGraphEdgeMapper;
import com.university.learning.mapper.KnowledgeGraphNodeMapper;
import com.university.learning.service.IKnowledgeGraphService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * 知识图谱服务 — 节点查询 + 掌握度注入 + 上下文构建
 */
@Service
@RequiredArgsConstructor
public class KnowledgeGraphServiceImpl implements IKnowledgeGraphService {

    private final KnowledgeGraphNodeMapper nodeMapper;
    private final KnowledgeGraphEdgeMapper edgeMapper;

    @Override
    public List<KnowledgeGraphNode> listNodes(String courseId) {
        return nodeMapper.selectList(
                new LambdaQueryWrapper<KnowledgeGraphNode>()
                        .eq(KnowledgeGraphNode::getCourseId, courseId));
    }

    @Override
    public List<KnowledgeGraphEdge> listEdges(String courseId) {
        return edgeMapper.selectList(
                new LambdaQueryWrapper<KnowledgeGraphEdge>()
                        .eq(KnowledgeGraphEdge::getCourseId, courseId));
    }

    @Override
    public Map<String, Object> getGraph(String courseId, Map<String, Float> masteries) {
        List<KnowledgeGraphNode> nodes = listNodes(courseId);
        List<KnowledgeGraphEdge> edges = listEdges(courseId);

        List<Map<String, Object>> nodeList = new ArrayList<>();
        for (KnowledgeGraphNode node : nodes) {
            float mastery = masteries.getOrDefault(node.getId(), 0f);
            Map<String, Object> n = new LinkedHashMap<>();
            n.put("id", node.getId());
            n.put("name", node.getName());
            n.put("description", node.getDescription());
            n.put("difficulty", node.getDifficulty());
            n.put("category", node.getCategory());
            n.put("mastery", mastery);
            n.put("sub_concepts", node.getSubConcepts());
            nodeList.add(n);
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("course_id", courseId);
        result.put("nodes", nodeList);
        result.put("edges", edges);
        return result;
    }

    @Override
    public Map<String, Object> getNodeCard(String courseId, String nodeId,
                                            Map<String, Float> masteries,
                                            int totalExercises, String lastPracticed) {
        KnowledgeGraphNode node = nodeMapper.selectById(nodeId);
        if (node == null) return null;

        List<KnowledgeGraphEdge> allEdges = listEdges(courseId);
        Map<String, KnowledgeGraphNode> nodeMap = listNodes(courseId).stream()
                .collect(Collectors.toMap(KnowledgeGraphNode::getId, n -> n));

        float mastery = masteries.getOrDefault(nodeId, 0f);

        // 前驱、后继、相关节点
        List<String> predecessors = allEdges.stream()
                .filter(e -> e.getTarget().equals(nodeId))
                .map(KnowledgeGraphEdge::getSource)
                .collect(Collectors.toList());

        List<String> successors = allEdges.stream()
                .filter(e -> e.getSource().equals(nodeId))
                .map(KnowledgeGraphEdge::getTarget)
                .collect(Collectors.toList());

        List<String> related = allEdges.stream()
                .filter(e -> (e.getSource().equals(nodeId) || e.getTarget().equals(nodeId))
                        && ("parallel".equals(e.getRelation()) || "extends".equals(e.getRelation())))
                .map(e -> e.getSource().equals(nodeId) ? e.getTarget() : e.getSource())
                .collect(Collectors.toList());

        // 节点信息
        Map<String, Object> nodeInfo = new LinkedHashMap<>();
        nodeInfo.put("id", node.getId());
        nodeInfo.put("name", node.getName());
        nodeInfo.put("description", node.getDescription());
        nodeInfo.put("difficulty", node.getDifficulty());
        nodeInfo.put("category", node.getCategory());
        nodeInfo.put("mastery", mastery);
        nodeInfo.put("sub_concepts", node.getSubConcepts());

        // 上下文
        Map<String, Object> context = new LinkedHashMap<>();
        context.put("prerequisites", detailList(predecessors, nodeMap, masteries));
        context.put("unlocks", detailList(successors, nodeMap, masteries));
        context.put("related", detailList(related, nodeMap, masteries));

        // 性能
        Map<String, Object> performance = new LinkedHashMap<>();
        performance.put("total_exercises", totalExercises);
        performance.put("last_practiced", lastPracticed);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("node", nodeInfo);
        result.put("graph_context", context);
        result.put("performance", performance);
        return result;
    }

    private List<Map<String, Object>> detailList(List<String> ids,
                                                  Map<String, KnowledgeGraphNode> nodeMap,
                                                  Map<String, Float> masteries) {
        return ids.stream().map(id -> {
            KnowledgeGraphNode n = nodeMap.get(id);
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", id);
            m.put("name", n != null ? n.getName() : id);
            m.put("mastery", masteries.getOrDefault(id, 0f));
            return m;
        }).collect(Collectors.toList());
    }

    @Override
    public void addNode(String courseId, Map<String, Object> nodeData) {
        KnowledgeGraphNode node = new KnowledgeGraphNode();
        node.setId((String) nodeData.get("id"));
        node.setName((String) nodeData.getOrDefault("name", nodeData.get("id")));
        node.setDescription((String) nodeData.getOrDefault("description", ""));
        node.setDifficulty(toInt(nodeData.get("difficulty"), 3));
        node.setCategory((String) nodeData.getOrDefault("category", ""));
        node.setCourseId(courseId);
        if (nodeData.containsKey("sub_concepts")) {
            node.setSubConcepts(nodeData.get("sub_concepts"));
        }
        nodeMapper.insert(node);
    }

    @Override
    public void addEdge(String courseId, Map<String, Object> edgeData) {
        KnowledgeGraphEdge edge = new KnowledgeGraphEdge();
        edge.setSource((String) edgeData.get("source"));
        edge.setTarget((String) edgeData.get("target"));
        edge.setRelation((String) edgeData.getOrDefault("relation", "depends_on"));
        edge.setRationale((String) edgeData.getOrDefault("rationale", ""));
        edge.setCourseId(courseId);
        edgeMapper.insert(edge);
    }

    private int toInt(Object value, int defaultValue) {
        if (value instanceof Number) return ((Number) value).intValue();
        if (value instanceof String) {
            try { return Integer.parseInt((String) value); } catch (NumberFormatException e) {}
        }
        return defaultValue;
    }
}
