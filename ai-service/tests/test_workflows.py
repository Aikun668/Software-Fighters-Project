"""Workflow orchestration tests."""
import pytest

from app.workflows.profile_workflow import ProfileWorkflow, DIMENSIONS, MIN_FILLED_DIMENSIONS


class TestProfileWorkflowStatus:
    """ProfileWorkflow.check_profile_status static method tests"""

    def test_empty_profile_not_complete(self):
        result = ProfileWorkflow.check_profile_status({})
        assert result["complete"] is False
        assert result["filled_dimensions"] == 0
        assert result["total_dimensions"] == 6

    def test_partial_profile_not_complete(self):
        profile = {
            "knowledge_base": 50,
            "cognitive_style": "visual",
            "learning_goal": "learn AI",
        }
        result = ProfileWorkflow.check_profile_status(profile)
        assert result["complete"] is False
        assert result["filled_dimensions"] == 3

    def test_full_profile_complete(self):
        profile = {
            "knowledge_base": 70,
            "cognitive_style": "visual",
            "learning_goal": "master ML",
            "weak_points": ["math"],
            "learning_pace": "fast",
            "interest_direction": ["NLP"],
        }
        result = ProfileWorkflow.check_profile_status(profile)
        assert result["complete"] is True
        assert result["filled_dimensions"] == 6

    def test_boundary_4_dimensions_is_complete(self):
        profile = {
            "knowledge_base": 50,
            "cognitive_style": "visual",
            "learning_goal": "learn AI",
            "weak_points": ["math"],
            "learning_pace": None,
            "interest_direction": [],
        }
        result = ProfileWorkflow.check_profile_status(profile)
        assert result["complete"] is True
        assert result["filled_dimensions"] == 4

    def test_empty_arrays_not_counted(self):
        profile = {
            "knowledge_base": 50,
            "cognitive_style": "visual",
            "weak_points": [],
            "interest_direction": [],
        }
        result = ProfileWorkflow.check_profile_status(profile)
        assert result["filled_dimensions"] == 2

    def test_invalid_keys_ignored(self):
        profile = {
            "knowledge_base": 50,
            "cognitive_style": "visual",
            "learning_goal": "learn AI",
            "weak_points": ["math"],
            "extra_field": "should be ignored",
        }
        result = ProfileWorkflow.check_profile_status(profile)
        assert result["filled_dimensions"] == 4
        assert "extra_field" not in result["dimensions"]


class TestProfileWorkflowDirectorRouting:
    """Director node routing logic tests"""

    def test_route_incomplete(self):
        state = {"profile_complete": False, "filled_dimensions": 2}
        route = ProfileWorkflow._route_after_director(state)
        assert route == "response"

    def test_route_complete(self):
        state = {"profile_complete": True, "filled_dimensions": 5}
        route = ProfileWorkflow._route_after_director(state)
        assert route == "complete"

    def test_route_falsy_complete(self):
        state = {"profile_complete": False, "filled_dimensions": 0}
        route = ProfileWorkflow._route_after_director(state)
        assert route == "response"


class TestResourceGenWorkflowInit:
    """ResourceGenWorkflow initialization tests"""

    def test_workflow_creates_agents(self):
        from app.workflows.resource_gen import ResourceGenWorkflow
        wf = ResourceGenWorkflow()
        assert wf.content_agent is not None
        assert wf.code_agent is not None
        assert wf.interactive_diagram_agent is not None
        assert wf.use_mock is False

    def test_graph_builds(self):
        from app.workflows.resource_gen import ResourceGenWorkflow
        wf = ResourceGenWorkflow()
        graph = wf._build_graph()
        assert graph is not None


class TestLearningPathWorkflowInit:
    """LearningPathWorkflow initialization tests"""

    def test_workflow_creates_agents(self):
        from app.workflows.learning_path import LearningPathWorkflow
        wf = LearningPathWorkflow()
        assert wf.path_agent is not None
        assert wf.content_agent is not None
        assert wf.use_mock is False

    def test_graph_builds(self):
        from app.workflows.learning_path import LearningPathWorkflow
        wf = LearningPathWorkflow()
        graph = wf._build_graph()
        assert graph is not None


