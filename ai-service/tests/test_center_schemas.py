import pytest

from app.centers.schemas import CenterTask, ExecutionPlan


class TestCenterTask:
    def test_create(self):
        task = CenterTask(mode="auto", intent="tutor_question", input="hello")
        assert task.mode == "auto"
        assert task.intent == "tutor_question"
        assert task.input == "hello"


class TestExecutionPlan:
    def test_clamps_tasks_to_max_intents(self):
        tasks = [CenterTask(mode="auto", intent="tutor_question", input=str(i)) for i in range(5)]
        plan = ExecutionPlan(tasks=tasks, max_intents=3)
        assert len(plan.tasks) == 3

    def test_default_max_intents_is_three(self):
        tasks = [CenterTask(mode="auto", intent="tutor_question", input=str(i)) for i in range(4)]
        plan = ExecutionPlan(tasks=tasks)
        assert len(plan.tasks) == 3

    def test_allows_fewer_tasks(self):
        tasks = [CenterTask(mode="auto", intent="tutor_question", input="x")]
        plan = ExecutionPlan(tasks=tasks)
        assert len(plan.tasks) == 1

    def test_is_clear_flag(self):
        plan = ExecutionPlan(is_clear=False, inquiry_question="你想做什么？")
        assert plan.is_clear is False
        assert plan.inquiry_question == "你想做什么？"
