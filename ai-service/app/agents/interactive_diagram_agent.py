"""InteractiveDiagramAgent — 结构化交互图解生成智能体

模型只输出受限的 Schema v1 图解数据（不生成、不执行 HTML/脚本）。
Vue 组件负责 SVG 渲染与节点点击交互。解析失败时回退到确定性结构化 fallback。
"""

import logging
from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.utils.prompt_loader import interpolate_variables
from app.services.diagram_schema import (
    DIAGRAM_SCHEMA_VERSION,
    validate_diagram_schema,
    validate_diagram_result,
    build_fallback_diagram,
)

logger = logging.getLogger(__name__)

DIAGRAM_TYPES = {
    "architecture": "模型架构图 — 展示网络层级结构、张量维度变化、数据流动方向",
    "training_dynamics": "训练动态 — 损失曲线、准确率变化、梯度分布随 epoch 的变化",
    "attention": "注意力流 — 自注意力权重热力图、跨注意力连接、token 间关系",
    "feature_space": "特征空间 — PCA/t-SNE 降维可视化、决策边界、聚类分布",
    "algorithm": "算法步骤 — 逐层/逐步骤演示算法执行过程，支持步骤前进/后退",
}


class InteractiveDiagramState(TypedDict, total=False):
    topic: str
    diagram_type: str
    student_profile: dict
    blocks: list[dict]
    diagram: dict
    diagram_source: str
    diagram_schema_version: str
    response: str


class InteractiveDiagramAgent(BaseAgent):
    """交互式可视化 Agent — 输出 interactive_diagram 类型 block（Schema v1）"""

    def __init__(self, config=None, use_mock_llm: bool = False,
                 model_profile=None):
        super().__init__(
            agent_name="interactive_diagram_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
            model_profile=model_profile,
        )

    def build_graph(self) -> "CompiledStateGraph":
        graph = StateGraph(InteractiveDiagramState)
        graph.add_node("generate", self._generate_node)
        graph.set_entry_point("generate")
        graph.set_finish_point("generate")
        return graph.compile()

    async def _generate_node(self, state: InteractiveDiagramState) -> dict:
        topic = state.get("topic", "")
        diagram_type = state.get("diagram_type", "architecture")
        student_profile = state.get("student_profile", {})

        if diagram_type not in DIAGRAM_TYPES:
            diagram_type = "architecture"

        type_desc = DIAGRAM_TYPES[diagram_type]

        sys_prompt = self._load_extra_prompt("system.yaml", key="system")
        user_tpl = self._load_extra_prompt("system.yaml", key="user_template")
        user_prompt = interpolate_variables(
            user_tpl,
            {
                "topic": topic,
                "diagram_type": diagram_type,
                "type_description": type_desc,
                "student_profile": self._format_profile(student_profile),
            },
        )

        result = await self._call_llm_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            expected_key="diagram",
            fallback={},
            validator=validate_diagram_result,
        )

        diagram = result.get("diagram") if isinstance(result, dict) else None
        source = "model"
        if not isinstance(diagram, dict) or validate_diagram_schema(diagram):
            diagram = build_fallback_diagram(topic, diagram_type)
            source = "fallback"

        blocks = [{
            "type": "interactive_diagram",
            "heading": diagram.get("title", topic),
            "content": diagram.get("summary", ""),
            "diagram": diagram,
        }]

        logger.info(
            f"InteractiveDiagramAgent generated {diagram_type} "
            f"diagram (source={source}, nodes={len(diagram.get('nodes', []))}) "
            f"for topic '{topic}'"
        )
        return {
            "blocks": blocks,
            "response": f"已生成「{topic}」的交互式可视化演示。",
            "diagram": diagram,
            "diagram_source": source,
            "diagram_schema_version": DIAGRAM_SCHEMA_VERSION,
        }
