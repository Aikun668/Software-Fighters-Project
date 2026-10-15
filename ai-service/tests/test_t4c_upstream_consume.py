"""T4-C 下游 center 消费 upstream_results（诊断→针对性练习）契约。"""

import pytest

from app.centers.exercise_center import ExerciseCenter
from app.centers.schemas import CenterTask


class _StubAgent:
    def __init__(self):
        self.run_state = None

    async def run(self, state):
        self.run_state = state
        return {"questions": [], "response": ""}


def _center(agent):
    return ExerciseCenter(exercise_agent=agent)


class TestConsumeDiagnoseUpstream:
    @pytest.mark.asyncio
    async def test_next_skill_sets_topic(self):
        agent = _StubAgent()
        cc = _center(agent)
        task = CenterTask(
            mode="exercise", intent="exercise_gen", input="出题", sequence=1,
            context={"upstream_results": [{
                "intent": "diagnose",
                "payload": {"next_skill": "动态规划", "mastery_vector": {"动态规划": 0.2}},
            }]},
        )
        await cc.execute(task)
        assert agent.run_state["topic"] == "动态规划"

    @pytest.mark.asyncio
    async def test_weak_mastery_sets_hard(self):
        agent = _StubAgent()
        cc = _center(agent)
        task = CenterTask(
            mode="exercise", intent="exercise_gen", input="出题", sequence=1,
            context={"upstream_results": [{
                "intent": "diagnose",
                "payload": {"next_skill": "动态规划", "mastery_vector": {"动态规划": 0.1}},
            }]},
        )
        await cc.execute(task)
        assert agent.run_state["difficulty"] == "hard"

    @pytest.mark.asyncio
    async def test_no_upstream_keeps_defaults(self):
        agent = _StubAgent()
        cc = _center(agent)
        task = CenterTask(
            mode="exercise", intent="exercise_gen", input="动态规划", sequence=1,
            params={"difficulty": "easy"},
        )
        await cc.execute(task)
        assert agent.run_state["topic"] == "动态规划"  # 用 input
        assert agent.run_state["difficulty"] == "easy"  # 用 params 默认
