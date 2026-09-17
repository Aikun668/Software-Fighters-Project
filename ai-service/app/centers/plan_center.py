import logging
from typing import Any, Awaitable, Callable, Optional

from app.centers.schemas import CenterResult, CenterTask

logger = logging.getLogger(__name__)


class PlanGenerationError(Exception):
    """计划生成完成但没有有效步骤，供 API 映射为现有 400 错误。"""


class PlanCenter:
    def __init__(
        self,
        goal_agent=None,
        decompose_agent=None,
        schedule_agent=None,
        adjustment_agent=None,
        graph_service=None,
        step_classifier=None,
    ):
        self.goal_agent = goal_agent
        self.decompose_agent = decompose_agent
        self.schedule_agent = schedule_agent
        self.adjustment_agent = adjustment_agent
        self.graph_service = graph_service
        self.step_classifier = step_classifier

    async def execute(self, task: CenterTask) -> CenterResult:
        context = task.context or {}
        student_profile = context.get("student_profile", {})
        topic = task.params.get("topic") or task.input

        if task.intent == "adjust_plan" and self.adjustment_agent is not None:
            return await self._run_adjustment(task, student_profile)

        return await self._run_new_plan(task, topic, student_profile)

    async def _run_new_plan(
        self,
        task: CenterTask,
        topic: str,
        student_profile: dict,
    ) -> CenterResult:
        try:
            goal_state = await self.goal_agent.run({
                "input": task.input,
                "context": task.params.get("context", ""),
                "student_profile": student_profile,
            })
            goal = {
                "goal_title": goal_state.get("goal_title", topic),
                "target_topic": goal_state.get("target_topic", topic),
                "target_level": goal_state.get("target_level", "understand"),
                "deadline": goal_state.get("deadline", ""),
                "motivation": goal_state.get("motivation", ""),
                "constraints": goal_state.get("constraints", []),
            }
        except Exception as e:
            logger.error(f"PlanCenter goal extraction failed: {e}")
            goal = {"goal_title": topic, "target_topic": topic, "target_level": "understand"}

        try:
            decompose_state = await self.decompose_agent.run({
                "topic": goal.get("target_topic", topic),
                "context": task.input,
                "student_profile": student_profile,
            })
            decomposition = {
                "macro_topics": decompose_state.get("macro_topics", []),
                "micro_skills": decompose_state.get("micro_skills", []),
                "prerequisites": decompose_state.get("prerequisites", []),
            }
        except Exception as e:
            logger.error(f"PlanCenter decomposition failed: {e}")
            decomposition = {}

        try:
            schedule_state = await self.schedule_agent.run({
                "goal": goal,
                "decomposition": decomposition,
                "student_profile": student_profile,
                "existing_plan": {},
            })
            steps = schedule_state.get("steps", [])
            payload = self._build_plan_payload(
                topic=topic,
                goal=goal,
                decomposition=decomposition,
                schedule_state=schedule_state,
            )
            return CenterResult(
                mode="plan",
                intent=task.intent,
                event_type="plan",
                payload=payload,
                agent="GoalAgent+DecomposeAgent+ScheduleAgent",
                sequence=task.sequence,
            )
        except Exception as e:
            logger.error(f"PlanCenter schedule failed: {e}")
            return CenterResult(
                mode="plan",
                intent=task.intent,
                event_type="error",
                error="计划编排失败",
                agent="ScheduleAgent",
                sequence=task.sequence,
            )

    @staticmethod
    def _build_plan_payload(
        *,
        topic: str,
        goal: dict,
        decomposition: dict,
        schedule_state: dict,
    ) -> dict:
        steps = schedule_state.get("steps", [])
        return {
            "type": "plan",
            "title": schedule_state.get("plan_title", f"{topic}学习计划"),
            "topic": topic,
            "total_steps": len(steps),
            "steps": steps,
            "milestones": schedule_state.get("milestones", []),
            "estimated_days": schedule_state.get("estimated_days", 7),
            "daily_capacity": schedule_state.get("daily_capacity", 3),
            "goal": goal,
            "concept_graph": decomposition,
            "summary": schedule_state.get("response", ""),
        }

    @staticmethod
    def _normalize_milestones(raw: list, total_steps: int) -> list[dict]:
        """将 ScheduleAgent 返回的里程碑标准化为 {milestone_id, after_step, description}。

        输入可能是字符串列表（LLM 直接输出）或已是正确格式。
        """
        if not raw:
            return []
        if isinstance(raw[0], dict) and "milestone_id" in raw[0]:
            return raw
        normalized = []
        n = len(raw)
        for i, item in enumerate(raw):
            desc = item if isinstance(item, str) else item.get("description", str(item))
            after_step = round(total_steps * (i + 1) / (n + 1))
            normalized.append({
                "milestone_id": f"m{i + 1}",
                "after_step": after_step,
                "description": desc,
            })
        return normalized

    async def _enrich_steps_with_nodes(self, steps: list[dict], course_id: str) -> list[dict]:
        """用知识图谱节点匹配每个 step 的 topic，打上 knowledge_node_id + suggested_resource_types。

        先用图谱已有节点精确匹配（name/id），匹配不到的用 LLM 分类兜底。
        """
        graph_service = self.graph_service
        if graph_service is None:
            from app.services.graph_service import get_graph_service
            graph_service = get_graph_service()

        step_classifier = self.step_classifier
        if step_classifier is None:
            from app.services.exercise_categorization_service import categorize_exercises
            step_classifier = categorize_exercises

        try:
            all_nodes = graph_service.load_skeleton().get("nodes", [])
            dynamic_nodes = graph_service._all_nodes(course_id)
        except Exception as exc:
            logger.warning(f"Graph service unavailable during step enrichment: {exc}")
            all_nodes = []
            dynamic_nodes = []
        node_lookup: dict[str, str] = {}
        node_category: dict[str, str] = {}
        for n in dynamic_nodes:
            name = (n.get("name") or "").strip().lower()
            nid = (n.get("id") or "").strip()
            if name and nid:
                node_lookup[name] = nid
                node_category[name] = (n.get("category") or "").strip()

        def _suggest_resources(topic: str, category: str) -> list[str]:
            """根据知识点类别建议资源类型。"""
            cat_lower = category.lower()
            if cat_lower in ("基础", "foundation", "概念", "concept"):
                return ["document", "mindmap", "exercise"]
            elif cat_lower in ("算法", "algorithm", "代码", "code"):
                return ["document", "code_demo", "exercise", "mindmap"]
            elif cat_lower in ("应用", "application", "实战", "practice"):
                return ["document", "case_study", "code_demo", "exercise"]
            elif cat_lower in ("数学", "math", "理论", "theory"):
                return ["document", "formula_sheet", "exercise"]
            else:
                return ["document", "mindmap", "exercise"]

        unknowns: list[dict] = []
        plan_steps: list[dict] = []
        for i, step in enumerate(steps):
            topic = (step.get("topic") or "").strip()
            matched_id = node_lookup.get(topic.lower(), "")
            matched_cat = node_category.get(topic.lower(), "")

            if matched_id:
                plan_steps.append({
                    "step_order": i + 1,
                    "topic": topic,
                    "knowledge_node_id": matched_id,
                    "status": step.get("status", "pending"),
                    "estimated_days": step.get("estimated_days", 1),
                    "topic_difficulty": step.get("topic_difficulty", 3),
                    "suggested_resource_types": _suggest_resources(topic, matched_cat),
                })
            else:
                unknowns.append({"index": i, "topic": topic, "step": step})

        if unknowns and all_nodes:
            slim_nodes = [{"id": n.get("id",""), "name": n.get("name",""), "description": n.get("description","")} for n in all_nodes]
            exercises = [{"question": u["topic"], "answer": "", "question_type": "short_answer"} for u in unknowns]
            try:
                results = await step_classifier(exercises, slim_nodes, course_id)
                result_map = {r["index"]: r.get("knowledge_node_id", "") for r in results}
            except Exception as exc:
                logger.warning(f"Step enrichment LLM fallback failed: {exc}")
                result_map = {}

            for u in unknowns:
                step = u["step"]
                nid = result_map.get(u["index"], "")
                plan_steps.append({
                    "step_order": u["index"] + 1,
                    "topic": u["topic"],
                    "knowledge_node_id": nid,
                    "status": step.get("status", "pending"),
                    "estimated_days": step.get("estimated_days", 1),
                    "topic_difficulty": step.get("topic_difficulty", 3),
                    "suggested_resource_types": _suggest_resources(u["topic"], ""),
                })

        plan_steps.sort(key=lambda s: s["step_order"])
        return plan_steps

    async def create_from_path(
        self,
        *,
        topic: str,
        course_id: str,
        student_profile: dict,
    ) -> dict:
        """API 一键生成学习计划专用入口。

        复用 Goal/Decompose/Schedule + _build_plan_payload 同一份生成逻辑，
        再叠加知识图谱节点匹配和里程碑标准化，输出完整 API payload。
        空 steps 抛 PlanGenerationError，由 API 层映射为 400 GENERATION_FAILED。
        """
        if self.goal_agent is None or self.decompose_agent is None or self.schedule_agent is None:
            raise PlanGenerationError("计划生成依赖未装配（Goal/Decompose/Schedule Agent）")

        try:
            goal_state = await self.goal_agent.run({
                "input": topic,
                "context": "",
                "student_profile": student_profile,
            })
        except Exception as e:
            logger.error(f"PlanCenter goal extraction failed: {e}")
            goal_state = {}

        goal = {
            "goal_title": goal_state.get("goal_title", topic),
            "target_topic": goal_state.get("target_topic", topic),
            "target_level": goal_state.get("target_level", "understand"),
            "deadline": goal_state.get("deadline", ""),
            "motivation": goal_state.get("motivation", ""),
            "constraints": goal_state.get("constraints", []),
        }

        try:
            decompose_state = await self.decompose_agent.run({
                "topic": goal.get("target_topic", topic),
                "context": topic,
                "student_profile": student_profile,
            })
        except Exception as e:
            logger.error(f"PlanCenter decomposition failed: {e}")
            decompose_state = {}

        decomposition = {
            "macro_topics": decompose_state.get("macro_topics", []),
            "micro_skills": decompose_state.get("micro_skills", []),
            "prerequisites": decompose_state.get("prerequisites", []),
        }

        try:
            schedule_state = await self.schedule_agent.run({
                "goal": goal,
                "decomposition": decomposition,
                "student_profile": student_profile,
                "existing_plan": {},
            })
        except Exception as e:
            logger.error(f"PlanCenter schedule failed: {e}")
            raise PlanGenerationError("计划编排失败，请稍后重试") from e

        steps = schedule_state.get("steps", [])
        if not steps:
            raise PlanGenerationError("未能生成学习计划，请确认输入更具体")

        payload = self._build_plan_payload(
            topic=goal.get("target_topic") or topic,
            goal=goal,
            decomposition=decomposition,
            schedule_state=schedule_state,
        )

        enriched_steps = await self._enrich_steps_with_nodes(steps, course_id)
        normalized_milestones = self._normalize_milestones(
            payload.get("milestones", []), len(enriched_steps)
        )

        return {
            "course_id": course_id,
            "total_steps": len(enriched_steps),
            "steps": enriched_steps,
            "title": payload["title"],
            "milestones": normalized_milestones,
            "estimated_days": payload["estimated_days"],
            "daily_capacity": payload["daily_capacity"],
            "concept_graph": payload["concept_graph"],
            "summary": payload["summary"],
        }

    async def _run_adjustment(self, task: CenterTask, student_profile: dict) -> CenterResult:
        try:
            state = await self.adjustment_agent.run({
                "original_plan": task.params.get("original_plan", {}),
                "mastery_vector": task.params.get("mastery_vector", {}),
                "days_idle": task.params.get("days_idle", 0),
                "events": task.params.get("events", []),
                "student_profile": student_profile,
            })
            return CenterResult(
                mode="plan",
                intent=task.intent,
                event_type="plan",
                payload={
                    "type": "plan_adjustment",
                    "adjustment_reason": state.get("adjustment_reason", ""),
                    "updated_steps": state.get("updated_steps", []),
                    "removed_steps": state.get("removed_steps", []),
                    "added_reviews": state.get("added_reviews", []),
                    "summary": state.get("response", ""),
                },
                agent="AdjustmentAgent",
                sequence=task.sequence,
            )
        except Exception as e:
            logger.error(f"PlanCenter adjustment failed: {e}")
            return CenterResult(
                mode="plan",
                intent=task.intent,
                event_type="error",
                error="计划调整失败",
                agent="AdjustmentAgent",
                sequence=task.sequence,
            )
