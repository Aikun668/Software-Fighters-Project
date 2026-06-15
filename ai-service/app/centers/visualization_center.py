import logging

from app.agents.mindmap_agent import MindMapAgent
from app.agents.visualize.visualize_pipeline import VisualizePipeline
from app.centers.schemas import CenterResult, CenterTask
from app.services.graph_service import GraphService, get_graph_service

logger = logging.getLogger(__name__)


class VisualizationCenter:
    def __init__(
        self,
        visualize_pipeline: VisualizePipeline | None = None,
        mindmap_agent: MindMapAgent | None = None,
        graph_service: GraphService | None = None,
    ):
        self.visualize_pipeline = visualize_pipeline
        self.mindmap_agent = mindmap_agent
        self.graph_service = graph_service

    async def execute(self, task: CenterTask) -> CenterResult:
        topic = task.params.get("topic") or task.input
        context = task.context or {}
        student_profile = context.get("student_profile", {})

        try:
            blocks = []

            if task.intent == "visualize":
                pipeline = self.visualize_pipeline or VisualizePipeline()
                viz_result = await pipeline.run(
                    question=task.input,
                    answer=f"关于{topic}的知识点讲解",
                )
                if viz_result.should_visualize:
                    blocks.append({
                        "type": viz_result.render_type,
                        "title": viz_result.title,
                        "code": viz_result.code,
                    })

            if task.intent == "knowledge_graph":
                graph_service = self.graph_service or get_graph_service()
                course_id = (
                    task.params.get("course_id")
                    or context.get("course_id")
                    or "ai_intro"
                )
                masteries = (
                    task.params.get("masteries")
                    or context.get("masteries")
                    or {}
                )
                graph = await graph_service.get_graph(
                    course_id=course_id, masteries=masteries
                )
                blocks.append({
                    "type": "knowledge_graph",
                    "graph": graph,
                })

            if task.intent == "mindmap":
                agent = self.mindmap_agent or MindMapAgent()
                state = await agent.run({
                    "topic": topic,
                    "student_profile": student_profile,
                    "outline": {"intro": f"{topic}知识结构", "subsections": []},
                })
                mindmap_blocks = state.get("blocks", [])
                blocks.extend(mindmap_blocks)

            return CenterResult(
                mode="visualization",
                intent=task.intent,
                event_type="visualization",
                payload={
                    "type": "visualization",
                    "topic": topic,
                    "blocks": blocks,
                },
                agent="VisualizationCenter",
                sequence=task.sequence,
            )
        except Exception as e:
            logger.error(f"VisualizationCenter failed: {e}")
            return CenterResult(
                mode="visualization",
                intent=task.intent,
                event_type="error",
                error="可视化生成失败",
                agent="VisualizationCenter",
                sequence=task.sequence,
            )
