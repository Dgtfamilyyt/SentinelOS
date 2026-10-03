"""
tests/test_goal_understanding.py
================================
Comprehensive tests for Master Prompt 02:
Goal Understanding & Task Ingestion layer.

Verifies:
 1. Simple goal extraction
 2. Complex goal extraction (mocked LLM)
 3. Objective creation distinct from action and criteria
 4. Success criteria formulation
 5. Constraint extraction
 6. Scope extraction and boundaries
 7. Mode detection
 8. Authorization context & anti-self-authorization security
 9. Missing information detection
10. Ambiguous goal handling (is_actionable=False)
11. Invalid model output handling (fallback safety)
12. Deterministic fast path
13. LLM structured-output path with markdown cleaning
14. Task creation from specification
15. AgentState receives the created task
16. CommandCenter integration
"""

import json
import pytest
from unittest.mock import MagicMock

from agent.goal import (
    AuthorizationContext,
    GoalUnderstandingEngine,
    TaskMode,
    TaskSpecification,
    TaskSpecificationValidator,
)
from agent.kernel import Agent
from agent.state import Task, TaskStatus
from core.command_center import CommandCenter


class TestGoalUnderstanding:

    # ----------------------------------------------------------------------
    # 1. Simple Goal Extraction
    # ----------------------------------------------------------------------
    def test_01_simple_goal_extraction(self):
        engine = GoalUnderstandingEngine()
        spec = engine.understand("List files in workspace")
        assert spec.objective == "Inspect and list files in the SentinelOS workspace"
        assert spec.action == "Enumerate workspace directory contents"
        assert spec.scope == {"type": "workspace", "path": "."}
        assert "read_only" in spec.constraints
        assert "workspace_sandbox" in spec.constraints
        assert len(spec.success_criteria) > 0
        assert spec.mode == TaskMode.GENERAL.value
        assert spec.authorization_context == AuthorizationContext.LOCAL.value
        assert spec.is_actionable is True
        assert spec.is_ambiguous is False
        assert spec.missing_information == []

    # ----------------------------------------------------------------------
    # 2. Complex Goal Extraction (Mocked LLM)
    # ----------------------------------------------------------------------
    def test_02_complex_goal_extraction_with_mock_llm(self):
        mock_client = MagicMock()
        mock_router = MagicMock()
        mock_router.choose.return_value = "mock_planner"

        mock_payload = {
            "objective": "Identify authentication bypass vulnerability in login endpoint",
            "action": "Analyze login handler source code and test input sanitization",
            "scope": {"type": "file", "target": "api/auth.py"},
            "constraints": ["read_only", "workspace_sandbox"],
            "success_criteria": ["Authentication logic analyzed", "Vulnerability report documented"],
            "mode": "cyber",
            "authorization_context": "local",
            "missing_information": [],
            "is_ambiguous": False,
            "is_actionable": True,
            "confidence": 0.95,
            "rationale_summary": "Security analysis of local API endpoint",
        }
        mock_client.generate.return_value = json.dumps(mock_payload)

        engine = GoalUnderstandingEngine(ai_client=mock_client, model_router=mock_router)
        spec = engine.understand("Audit api/auth.py for authentication bypasses")

        assert spec.objective == "Identify authentication bypass vulnerability in login endpoint"
        assert spec.action == "Analyze login handler source code and test input sanitization"
        assert spec.scope == {"type": "file", "target": "api/auth.py"}
        assert spec.mode == TaskMode.CYBER.value
        assert spec.is_actionable is True
        mock_client.generate.assert_called_once()

    # ----------------------------------------------------------------------
    # 3. Objective Creation Distinct from Action
    # ----------------------------------------------------------------------
    def test_03_objective_creation_distinct_from_action(self):
        engine = GoalUnderstandingEngine()
        spec = engine.understand("Check why the SentinelOS tests are failing.")

        assert spec.objective == "Identify the cause of failing SentinelOS tests"
        assert spec.action == "Execute test suite and analyze failure tracebacks"
        assert spec.objective != spec.action
        assert any("telemetry" in sc or "identified" in sc for sc in spec.success_criteria)
        assert spec.mode == TaskMode.DEVELOPMENT.value

    # ----------------------------------------------------------------------
    # 4. Success Criteria Creation
    # ----------------------------------------------------------------------
    def test_04_success_criteria_creation(self):
        engine = GoalUnderstandingEngine()
        spec = engine.understand("create a project folder called test123")

        assert len(spec.success_criteria) >= 1
        assert any("test123" in sc for sc in spec.success_criteria)
        assert spec.scope.get("path") == "test123"

    # ----------------------------------------------------------------------
    # 5. Constraint Extraction
    # ----------------------------------------------------------------------
    def test_05_constraint_extraction(self):
        engine = GoalUnderstandingEngine()
        spec = engine.understand("read config/settings.py")

        assert "read_only" in spec.constraints
        assert "workspace_sandbox" in spec.constraints
        assert spec.scope == {"type": "file", "path": "config/settings.py"}

    # ----------------------------------------------------------------------
    # 6. Scope Extraction
    # ----------------------------------------------------------------------
    def test_06_scope_extraction(self):
        engine = GoalUnderstandingEngine()
        spec = engine.understand("create folder my_agent_demo")

        assert spec.scope == {"type": "directory", "path": "my_agent_demo"}
        assert spec.action == "Create new folder 'my_agent_demo' in workspace"

    # ----------------------------------------------------------------------
    # 7. Mode Detection
    # ----------------------------------------------------------------------
    def test_07_mode_detection(self):
        assert TaskMode.normalize("chat") == TaskMode.GENERAL.value
        assert TaskMode.normalize("coding") == TaskMode.DEVELOPMENT.value
        assert TaskMode.normalize("soc") == TaskMode.DEFENSIVE.value
        assert TaskMode.normalize("red") == TaskMode.AUTHORIZED_LAB.value
        assert TaskMode.normalize("purple") == TaskMode.ANALYSIS.value
        assert TaskMode.normalize("cyber") == TaskMode.CYBER.value

    # ----------------------------------------------------------------------
    # 8. Authorization Context & Anti-Self-Authorization Security
    # ----------------------------------------------------------------------
    def test_08_authorization_context_and_security(self):
        # A model claiming "explicitly_authorized" for an external target without caller context
        # must be demoted to "unspecified" or "restricted"
        malicious_or_hallucinated_data = {
            "objective": "Attack external banking server",
            "scope": {"type": "remote", "target": "bank.internal"},
            "authorization_context": "explicitly_authorized",  # Self-granted!
            "mode": "authorized_lab",
        }
        spec = TaskSpecificationValidator.validate(malicious_or_hallucinated_data, context=None)
        assert spec.authorization_context != "explicitly_authorized"
        assert spec.authorization_context in (AuthorizationContext.UNSPECIFIED.value, AuthorizationContext.RESTRICTED.value)

        # When caller context explicitly provides authorization, it is respected
        valid_context = {
            "authorized_targets": ["bank.internal"],
            "authorization_level": "lab",
        }
        spec_valid = TaskSpecificationValidator.validate(malicious_or_hallucinated_data, context=valid_context)
        assert spec_valid.authorization_context == "explicitly_authorized"

    # ----------------------------------------------------------------------
    # 9. Missing Information Detection & 10. Ambiguous Goal Handling
    # ----------------------------------------------------------------------
    def test_09_10_missing_info_and_ambiguity(self):
        engine = GoalUnderstandingEngine()
        spec = engine.understand("Scan the server.")

        assert spec.is_ambiguous is True
        assert spec.is_actionable is False
        assert len(spec.missing_information) > 0
        assert "target_host_or_ip" in spec.missing_information
        assert spec.scope == {"type": "unknown"}

        # When converted to Task, status must be BLOCKED
        task = spec.to_task()
        assert task.status == TaskStatus.BLOCKED
        assert "Awaiting missing information" in task.conclusion

    # ----------------------------------------------------------------------
    # 11. Invalid Model Output Handling (Fallback Safety)
    # ----------------------------------------------------------------------
    def test_11_invalid_model_output_handling(self):
        mock_client = MagicMock()
        mock_client.generate.return_value = "This is not JSON at all! Just raw rambling."

        engine = GoalUnderstandingEngine(ai_client=mock_client)
        spec = engine.understand("Debug the authentication database connection")

        assert spec.objective is not None
        assert len(spec.objective) > 0
        assert spec.mode == TaskMode.DEVELOPMENT.value
        assert spec.is_actionable is True

    # ----------------------------------------------------------------------
    # 12. Deterministic Fast Path
    # ----------------------------------------------------------------------
    def test_12_deterministic_fast_path(self):
        mock_client = MagicMock()
        mock_client.generate.side_effect = AssertionError("LLM should not be called on fast path")

        engine = GoalUnderstandingEngine(ai_client=mock_client)
        spec = engine.understand("show workspace files")

        assert spec.objective == "Inspect and list files in the SentinelOS workspace"
        assert spec.is_actionable is True
        mock_client.generate.assert_not_called()

    # ----------------------------------------------------------------------
    # 13. LLM Structured Output with Markdown Fences
    # ----------------------------------------------------------------------
    def test_13_llm_markdown_fences_cleaned(self):
        mock_client = MagicMock()
        mock_client.generate.return_value = """```json
{
  "objective": "Review network architecture design",
  "action": "Analyze network topology diagrams",
  "scope": {"type": "workspace", "path": "docs"},
  "constraints": ["read_only"],
  "success_criteria": ["Architecture review completed"],
  "mode": "research",
  "authorization_context": "local",
  "missing_information": [],
  "is_ambiguous": false,
  "is_actionable": true
}
```"""
        engine = GoalUnderstandingEngine(ai_client=mock_client)
        spec = engine.understand("Review the network architecture design in docs")

        assert spec.objective == "Review network architecture design"
        assert spec.mode == TaskMode.RESEARCH.value
        assert spec.is_actionable is True

    # ----------------------------------------------------------------------
    # 14. Task Creation from Specification
    # ----------------------------------------------------------------------
    def test_14_task_creation_from_specification(self):
        spec = TaskSpecification(
            objective="Audit dependencies for CVEs",
            action="Scan requirements.txt against vulnerability DB",
            scope={"type": "file", "path": "requirements.txt"},
            constraints=["read_only"],
            success_criteria=["CVE audit completed", "report generated"],
            mode=TaskMode.CYBER.value,
            authorization_context=AuthorizationContext.LOCAL.value,
            metadata={"source": "cli"},
        )
        task = spec.to_task()

        assert isinstance(task, Task)
        assert task.objective == "Audit dependencies for CVEs"
        assert task.constraints == ["read_only"]
        assert task.success_criteria == ["CVE audit completed", "report generated"]
        assert task.scope == {"type": "file", "path": "requirements.txt"}
        assert task.mode == TaskMode.CYBER.value
        assert task.authorization_level == AuthorizationContext.LOCAL.value
        assert task.status == TaskStatus.CREATED

    # ----------------------------------------------------------------------
    # 15. AgentState Receives Created Task
    # ----------------------------------------------------------------------
    def test_15_agent_state_receives_task(self):
        engine = GoalUnderstandingEngine()
        task = engine.ingest("Inspect the workspace.")

        agent = Agent()
        agent.state.set_task(task)

        assert agent.state.active_task is task
        assert agent.state.objective == "Inspect and list files in the SentinelOS workspace"
        assert agent.state.lifecycle_state == TaskStatus.CREATED
        assert "read_only" in agent.state.active_task.constraints

    # ----------------------------------------------------------------------
    # 16. CommandCenter Integration
    # ----------------------------------------------------------------------
    def test_16_command_center_integration(self):
        center = CommandCenter()

        # 1. understand_goal()
        spec = center.understand_goal("create a project folder called test123")
        assert spec.objective == "Create project folder 'test123'"
        assert spec.scope.get("path") == "test123"
        assert spec.is_actionable is True

        # 2. ingest_task()
        task = center.ingest_task("Scan the server.")
        assert task.objective == "Perform network scan against server"
        assert task.status == TaskStatus.BLOCKED
        assert "target_host_or_ip" in task.metadata["missing_information"]
