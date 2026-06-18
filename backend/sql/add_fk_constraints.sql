-- =============================================
-- 给 node_id 字段加外键约束
-- =============================================

-- plan_steps.node_id 允许 NULL（复习步骤等可能不关联图谱节点）
ALTER TABLE plan_steps MODIFY COLUMN node_id VARCHAR(100) NULL DEFAULT NULL;

-- plan_steps.node_id → knowledge_graph_nodes.id
ALTER TABLE plan_steps
    ADD CONSTRAINT fk_plan_steps_node
    FOREIGN KEY (node_id) REFERENCES knowledge_graph_nodes(id)
    ON DELETE SET NULL;

-- node_masteries.node_id → knowledge_graph_nodes.id
ALTER TABLE node_masteries
    ADD CONSTRAINT fk_node_masteries_node
    FOREIGN KEY (node_id) REFERENCES knowledge_graph_nodes(id)
    ON DELETE CASCADE;
