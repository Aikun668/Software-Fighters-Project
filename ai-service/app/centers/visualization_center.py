import asyncio
import logging

from app.agents.mindmap_agent import MindMapAgent
from app.agents.tutor_agent import TutorAgent
from app.agents.visualize.visualize_pipeline import VisualizePipeline
from app.centers.schemas import CenterResult, CenterTask
from app.services.graph_service import GraphService, get_graph_service

logger = logging.getLogger(__name__)

_VIS_HARD_TIMEOUT = 45  # 可视化硬超时（秒），不阻塞后续任务
_TUTOR_TIMEOUT = 120     # 先导内容生成超时


class VisualizationCenter:
    def __init__(
        self,
        visualize_pipeline: VisualizePipeline | None = None,
        mindmap_agent: MindMapAgent | None = None,
        graph_service: GraphService | None = None,
        tutor_agent: "TutorAgent | None" = None,
        use_mock_llm: bool = False,
    ):
        self.visualize_pipeline = visualize_pipeline
        self.mindmap_agent = mindmap_agent
        self.graph_service = graph_service
        self._tutor_agent = tutor_agent
        # P0-B：惰性构造的 Agent / Pipeline 继承本旗标
        self.use_mock_llm = use_mock_llm

    async def execute(self, task: CenterTask) -> CenterResult:
        topic = task.params.get("topic") or task.input
        context = task.context or {}
        student_profile = context.get("student_profile", {})
        messages = context.get("messages", [])
        style = context.get("style", "standard")

        try:
            blocks = []

            if task.intent == "visualize":
                try:
                    if self._tutor_agent is None:
                        self._tutor_agent = TutorAgent(use_mock_llm=self.use_mock_llm)
                    tutor = self._tutor_agent
                    try:
                        tutor_state = await asyncio.wait_for(
                            tutor.run({
                                "messages": messages,
                                "student_profile": student_profile,
                                "style": style,
                            }),
                            timeout=_TUTOR_TIMEOUT,
                        )
                        answer = tutor_state.get("response", "")
                    except (asyncio.TimeoutError, Exception) as e:
                        logger.warning("可视化前置 tutor 失败: %s，使用问题文本降级", e)
                        answer = task.input

                    # answer 为空壳 summary（如 ContentAgent 的"已为您生成...共 X 个内容块"）
                    # 时，用 question 驱动 AnalysisAgent，避免因"答案<100字"被误杀
                    if len(answer.strip()) < 100:
                        answer = f"用户问题：{task.input}\n（基于问题本身推断可视化需求）"

                    async with asyncio.timeout(_VIS_HARD_TIMEOUT):
                        pipeline = self.visualize_pipeline or VisualizePipeline(
                            use_mock_llm=self.use_mock_llm
                        )
                        viz_result = await pipeline.run(
                            question=task.input,
                            answer=answer,
                        )
                    if viz_result.should_visualize:
                        block = {
                            "type": viz_result.render_type,
                            "title": viz_result.title,
                            "code": viz_result.code,
                        }
                        if viz_result.warning:
                            block["warning"] = viz_result.warning
                        blocks.append(block)
                except asyncio.TimeoutError:
                    logger.warning(
                        "可视化超时 (%.0fs)，跳过图解: %s", _VIS_HARD_TIMEOUT, topic
                    )
                    return CenterResult(
                        mode="visualization",
                        intent=task.intent,
                        event_type="error",
                        error="可视化生成超时，已跳过",
                        payload={"type": "visualization", "topic": topic, "blocks": []},
                        agent="VisualizationCenter",
                        sequence=task.sequence,
                    )

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
                agent = self.mindmap_agent or MindMapAgent(use_mock_llm=self.use_mock_llm)
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
                error="可视化生成失败，请稍后重试",
                payload={"type": "visualization", "topic": topic, "blocks": []},
                agent="VisualizationCenter",
                sequence=task.sequence,
            )
