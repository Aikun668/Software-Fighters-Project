import logging
from datetime import date, datetime, timezone

from app.centers.schemas import CenterResult, CenterTask
from app.services.plan_service import PlanService

logger = logging.getLogger(__name__)


class PlanGenerationError(Exception):
    """计划生成完成但没有有效步骤，供 API 映射为现有 400 错误。"""


class PlanNotFoundError(Exception):
    """计划或步骤数据缺失，供 API 映射为 404（消息原样透出）。"""


class PlanCenter:
    def __init__(
        self,
        goal_agent=None,
        decompose_agent=None,
        schedule_agent=None,
        adjustment_agent=None,
        graph_service=None,
        step_classifier=None,
        plan_service=None,
        exercise_center=None,
    ):
        self.goal_agent = goal_agent
        self.decompose_agent = decompose_agent
        self.schedule_agent = schedule_agent
        self.adjustment_agent = adjustment_agent
        self.graph_service = graph_service
        self.step_classifier = step_classifier
        self.plan_service = plan_service or PlanService
        self.exercise_center = exercise_center

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
            payload = await self._generate_base_plan(
                user_input=task.input,
                topic=topic,
                context=task.params.get("context", ""),
                student_profile=student_profile,
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
            logger.error(f"PlanCenter base plan orchestration failed: {e}")
            return CenterResult(
                mode="plan",
                intent=task.intent,
                event_type="error",
                error="计划编排失败",
                agent="GoalAgent+DecomposeAgent+ScheduleAgent",
                sequence=task.sequence,
            )

    async def _generate_base_plan(
        self,
        *,
        user_input: str,
        topic: str,
        context: str,
        student_profile: dict,
    ) -> dict:
        """唯一执行 Goal → Decompose → Schedule 的位置，返回未增强 payload。

        - Goal 失败：降级为默认 goal（target_topic=topic）
        - Decompose 失败：降级为默认 decomposition（空 dict）
        - Schedule 失败：抛 PlanGenerationError，由调用者映射为对应错误形态
        """
        try:
            goal_state = await self.goal_agent.run({
                "input": user_input,
                "context": context,
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
                "context": user_input,
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
        except Exception as e:
            logger.error(f"PlanCenter schedule failed: {e}")
            raise PlanGenerationError("计划编排失败，请稍后重试") from e

        return self._build_plan_payload(
            topic=goal.get("target_topic") or topic,
            goal=goal,
            decomposition=decomposition,
            schedule_state=schedule_state,
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
        else:
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

        复用 _generate_base_plan 同一份 Goal/Decompose/Schedule 编排，
        再叠加知识图谱节点匹配和里程碑标准化，输出完整 API payload。
        空 steps 抛 PlanGenerationError，由 API 层映射为 400 GENERATION_FAILED。
        """
        if self.goal_agent is None or self.decompose_agent is None or self.schedule_agent is None:
            raise PlanGenerationError("计划生成依赖未装配（Goal/Decompose/Schedule Agent）")

        payload = await self._generate_base_plan(
            user_input=topic,
            topic=topic,
            context="",
            student_profile=student_profile,
        )

        steps = payload.get("steps", [])
        if not steps:
            raise PlanGenerationError("未能生成学习计划，请确认输入更具体")

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

    # ── 计划端点业务入口（从 internal_api 收口迁入） ──────────

    async def today_tasks(
        self,
        *,
        plan_id: int,
        plan: dict,
        steps: list[dict],
        start_date: str | None,
        masteries: dict,
    ) -> dict:
        """今日任务 payload：按累计 estimated_days 定位当天步骤 + 资源建议。"""
        if not plan:
            raise PlanNotFoundError("计划不存在")

        today = date.today()
        day_index = self._day_index(start_date, plan, today)
        completed_steps = plan.get("completed_steps") or 0
        total_steps = len(steps) if steps else plan.get("total_steps", 0)

        today_steps = self.plan_service.select_today_steps(
            steps, day_index=day_index, completed_steps=completed_steps,
            total_steps=total_steps, masteries=masteries or {},
        )

        return {
            "plan_id": plan_id,
            "today": today.isoformat(),
            "day_index": day_index,
            "total_days_elapsed": day_index + 1,
            "steps_due_today": today_steps,
            "resource_suggestions": self.plan_service.build_resource_suggestions(today_steps),
            "next_milestone": self.plan_service.compute_next_milestone(plan, completed_steps),
            "summary": (
                f"今日有 {len(today_steps)} 个学习步骤"
                if today_steps
                else "今日无待完成步骤，继续保持！"
            ),
        }

    @staticmethod
    def _day_index(start_date: str | None, plan: dict, today: date) -> int:
        start_str = start_date or plan.get("start_date") or plan.get("created_at")
        start = today
        if isinstance(start_str, str):
            try:
                start = datetime.fromisoformat(start_str.replace("Z", "+00:00")).date()
            except (ValueError, TypeError):
                start = today
        return max((today - start).days, 0)

    async def plan_status(self, *, plan: dict, steps: list[dict]) -> dict:
        """计划状态 payload：软着陆检测 + 步骤衰减 + 里程碑进度。"""
        if not plan:
            raise PlanNotFoundError("计划不存在")

        days_idle = self._days_idle(plan)
        paused_steps = [s for s in steps if s.get("status") in ("paused", "in_progress")]

        soft_landing = None
        if plan.get("status") == "paused" and days_idle > 0:
            soft_landing = self.plan_service.soft_landing(
                [self._decay_input(s) for s in paused_steps], days_idle,
            )
            soft_landing["days_idle"] = days_idle

        completed_steps = plan.get("completed_steps") or 0
        next_milestone = self.plan_service.compute_next_milestone(plan, completed_steps)

        return {
            "plan_id": plan.get("id"),
            "user_id": plan.get("user_id"),
            "status": plan.get("status"),
            "total_steps": plan.get("total_steps"),
            "completed_steps": completed_steps,
            "days_idle": days_idle,
            "soft_landing": soft_landing,
            "steps": [
                self._status_step_entry(s, days_idle) for s in steps
            ],
            "next_milestone": next_milestone,
            "milestone_progress": self.plan_service.build_milestone_progress(
                completed_steps, next_milestone,
            ),
        }

    @staticmethod
    def _days_idle(plan: dict) -> int:
        last_activity = plan.get("last_activity_at")
        if not last_activity:
            return 0
        try:
            dt = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
        except (ValueError, TypeError, AttributeError):
            return 0
        return (datetime.now(timezone.utc) - dt).days

    @staticmethod
    def _decay_input(step: dict) -> dict:
        return {
            "topic": step.get("topic"),
            "mastery_current": step.get("mastery_current") or 0,
            "topic_difficulty": step.get("topic_difficulty") or 3,
            "review_count": step.get("review_count") or 0,
        }

    def _status_step_entry(self, step: dict, days_idle: int) -> dict:
        entry = {
            "id": step.get("id"),
            "step_order": step.get("step_order"),
            "topic": step.get("topic"),
            "knowledge_node_id": step.get("knowledge_node_id"),
            "status": step.get("status"),
            "topic_difficulty": step.get("topic_difficulty"),
            "mastery_current": step.get("mastery_current"),
        }
        if step.get("status") in ("paused", "in_progress") and days_idle > 0:
            entry["decayed_mastery"] = self.plan_service.estimate_decay(
                step.get("mastery_current") or 0, days_idle,
                step.get("topic_difficulty") or 3, step.get("review_count") or 0,
            )
        return entry

    async def review_schedule(
        self, *, plan_id: int, steps: list[dict], days_ahead: int,
    ) -> dict:
        """复习日程 payload：直接以 dict 传入 PlanService（步骤字段缺省在 Service 内兜底）。"""
        schedule = self.plan_service.get_review_schedule(steps, days_ahead)
        counts = self.plan_service.summarize_review_schedule(schedule)
        return {
            "plan_id": plan_id,
            "days_ahead": days_ahead,
            "total_reviews": len(schedule),
            "high_urgency": counts["high"],
            "medium_urgency": counts["medium"],
            "schedule": schedule,
        }

    async def update_progress(
        self,
        *,
        plan_id: int,
        plan: dict,
        steps: list[dict],
        masteries: dict,
        step_id: int | None,
        step_order: int | None,
        status: str,
        score: float | None,
        activity_type: str,
        duration_minutes: int,
    ) -> dict:
        """掌握度更新 payload：定位步骤 → 算掌握度 → 返回更新后步骤 + 里程碑进度。"""
        if not plan:
            raise PlanNotFoundError("计划不存在")

        target_step, step_idx = self.plan_service.find_step(
            steps, step_id=step_id, step_order=step_order,
        )
        if target_step is None:
            raise PlanNotFoundError(
                f"步骤 step_id={step_id} step_order={step_order} 不存在"
            )

        masteries = masteries or {}
        knowledge_node_id = target_step.get("knowledge_node_id", "")
        old_mastery = self._old_mastery(masteries, target_step, knowledge_node_id)
        event_type = "exercise_done" if activity_type in ("exercise", "quiz") else "resource_viewed"
        new_mastery = self.plan_service.update_mastery(old_mastery, event_type, score=score)

        mastery_updates = {}
        if knowledge_node_id:
            mastery_updates[knowledge_node_id] = {
                "old_mastery": old_mastery,
                "new_mastery": new_mastery,
                "delta": round(new_mastery - old_mastery, 2),
                "event_type": event_type,
            }

        updated_steps = list(steps)
        if step_idx >= 0:
            updated_steps[step_idx] = {
                **target_step,
                "status": status,
                **({"score": score} if score is not None else {}),
                "mastery_current": new_mastery,
                "activity_type": activity_type,
                "duration_minutes": duration_minutes,
            }

        completed_count = sum(1 for s in updated_steps if s.get("status") == "completed")
        total_steps = plan.get("total_steps", len(steps))

        return {
            "plan_id": plan_id,
            "updated_step": {
                "step_order": target_step.get("step_order"),
                "topic": target_step.get("topic"),
                "knowledge_node_id": knowledge_node_id,
                "status": status,
                "score": score,
                "mastery_current": new_mastery,
                "activity_type": activity_type,
                "duration_minutes": duration_minutes,
            },
            "mastery_updates": mastery_updates,
            "completed_steps": completed_count,
            "total_steps": total_steps,
            "progress_pct": round(completed_count / max(total_steps, 1) * 100),
            "next_milestone": self.plan_service.compute_next_milestone(plan, completed_count),
            "updated_steps": updated_steps,
        }

    @staticmethod
    def _old_mastery(masteries: dict, step: dict, knowledge_node_id: str) -> float:
        if not knowledge_node_id:
            return 0.5
        return masteries.get(knowledge_node_id, step.get("mastery_current", 0.5))

    async def node_status_change(
        self,
        *,
        plan_id: int,
        plan: dict,
        steps: list[dict],
        masteries: dict,
        node_id: str,
        old_status: str,
        new_status: str,
    ) -> dict:
        """图谱节点状态变化 → 计划步骤联动 payload。"""
        if not plan or not steps:
            raise PlanNotFoundError("计划或步骤数据缺失")

        outcome = self.plan_service.apply_node_status_change(
            steps=steps, node_id=node_id, new_status=new_status, old_status=old_status,
            masteries=masteries or {}, plan_status=plan.get("status", "active"),
        )
        completed = outcome["completed_steps"]
        total = outcome["total_steps"]

        return {
            "plan_id": plan_id,
            "node_id": node_id,
            "new_status": new_status,
            **outcome,
            "progress_pct": round(completed / max(total, 1) * 100),
            "next_milestone": self.plan_service.compute_next_milestone(plan, completed),
            "summary": (
                f"节点状态变更影响 {outcome['affected_steps_count']} 个计划步骤"
                if outcome["affected_steps_count"]
                else "此节点状态变更不影响当前计划的步骤"
            ),
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
