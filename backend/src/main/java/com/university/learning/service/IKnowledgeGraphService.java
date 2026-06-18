package com.university.learning.service;

import com.university.learning.entity.KnowledgeGraphEdge;
import com.university.learning.entity.KnowledgeGraphNode;

import java.util.List;
import java.util.Map;

/**
 * 知识图谱服务 — 纯Java，不调Python
 */
public interface IKnowledgeGraphService {

    /** 获取课程所有节点 */
    List<KnowledgeGraphNode> listNodes(String courseId);

    /** 获取课程所有边 */
    List<KnowledgeGraphEdge> listEdges(String courseId);

    /** 获取完整图谱（节点+边+掌握度） */
    Map<String, Object> getGraph(String courseId, Map<String, Float> masteries);

    /** 获取节点卡片（含上下文） */
    Map<String, Object> getNodeCard(String courseId, String nodeId,
                                     Map<String, Float> masteries,
                                     int totalExercises, String lastPracticed);
}
