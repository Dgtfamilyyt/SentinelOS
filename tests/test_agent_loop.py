"""
tests/test_agent_loop.py
========================
Integration-style tests for the agent loop and its components.

Uses mocks so no real tools or LLM are needed.
"""

import pytest
from unittest.mock import MagicMock, patch

from agent.state import (
    AgentTask,
    AgentState,
    TaskStep,
    StepResult,
    TaskStatus,
    StepStatus,
    FailureClass,
    VerificationStatus,
)
from agent.executor  import StepExecutor
from agent.verifier  import StateVerifier
from agent.recovery  import FailureRecovery
from agent.loop      import AgentLoop, _summarize_output


# ---------------------------------------------------------------------------
# StepExecutor tests
# ---------------------------------------------------------------------------

class TestStepExecutor:

    def _make_executor(self, tool_result: dict, tool_names=None):
        tool_manager        = MagicMock()
        tool_manager.names  = MagicMock(return_value=tool_names or ["ping"])
        tool_manager.execute= MagicMock(return_value=tool_result)
        return StepExecutor(tool_manager)

    def test_execute_success(self):
        executor = self._make_executor({"success": True, "result": "pong"})
        step     = TaskStep(tool_name="ping", parameters={"host": "127.0.0.1"})
        task     = AgentTask(goal="Test")
        result   = executor.execute(step, task)
        assert result.success
        assert result.raw_output == "pong"

    def test_execute_tool_not_found(self):
        executor = self._make_executor({}, tool_names=[])
        step     = TaskStep(tool_name="nonexistent")
        task     = AgentTask(goal="Test")
        result   = executor.execute(step, task)
        assert not result.success
        assert result.failure_class == FailureClass.ENVIRONMENTAL

    def test_execute_tool_returns_failure(self):
        executor = self._make_executor({"success": False, "error": "timeout"})
        step     = TaskStep(tool_name="ping", parameters={})
        task     = AgentTask(goal="Test")
        result   = executor.execute(step, task)
        assert not result.success
        assert result.failure_class == FailureClass.TRANSIENT

    def test_execute_handles_exception(self):
        tool_manager        = MagicMock()
        tool_manager.names  = MagicMock(return_value=["ping"])
        tool_manager.execute= MagicMock(side_effect=RuntimeError("boom"))
        executor = StepExecutor(tool_manager)
        step     = TaskStep(tool_name="ping", parameters={})
        task     = AgentTask(goal="Test")
        result   = executor.execute(step, task)
        assert not result.success
        assert "boom" in result.error

    def test_failure_classification_transient(self):
        assert StepExecutor._classify("Connection timed out") == FailureClass.TRANSIENT
        assert StepExecutor._classify("resource temporarily unavailable") == FailureClass.TRANSIENT

    def test_failure_classification_environmental(self):
        assert StepExecutor._classify("command not found") == FailureClass.ENVIRONMENTAL
        assert StepExecutor._classify("Permission denied") == FailureClass.ENVIRONMENTAL

    def test_failure_classification_logical(self):
        assert StepExecutor._classify("invalid parameter value") == FailureClass.LOGICAL


# ---------------------------------------------------------------------------
# StateVerifier tests
# ---------------------------------------------------------------------------

class TestStateVerifier:

    def _make_verifier(self):
        tool_manager = MagicMock()
        return StateVerifier(tool_manager, ai_engine=None)

    def test_no_condition_returns_skipped(self):
        verifier = self._make_verifier()
        step     = TaskStep(tool_name="ping")  # No verify_condition
        result   = StepResult(step_id="s1", tool_name="ping", parameters={}, success=True)
        status, detail = verifier.verify(step, result, AgentTask(goal="test"))
        assert status == VerificationStatus.SKIPPED

    def test_condition_contains_passes(self):
        verifier = self._make_verifier()
        step     = TaskStep(tool_name="ping", verify_condition="contains open")
        result   = StepResult(
            step_id="s1", tool_name="ping", parameters={},
            success=True, raw_output="Port 22 is open"
        )
        status, detail = verifier.verify(step, result, AgentTask(goal="test"))
        assert status == VerificationStatus.PASSED

    def test_condition_contains_fails(self):
        verifier = self._make_verifier()
        step     = TaskStep(tool_name="ping", verify_condition="contains open")
        result   = StepResult(
            step_id="s1", tool_name="ping", parameters={},
            success=True, raw_output="all ports closed"
        )
        status, detail = verifier.verify(step, result, AgentTask(goal="test"))
        assert status == VerificationStatus.FAILED

    def test_no_error_condition(self):
        verifier = self._make_verifier()
        step     = TaskStep(tool_name="run_command", verify_condition="no error in output")
        result   = StepResult(
            step_id="s1", tool_name="run_command", parameters={},
            success=True, raw_output="Files copied successfully."
        )
        status, _ = verifier.verify(step, result, AgentTask(goal="test"))
        assert status == VerificationStatus.PASSED

    def test_check_condition_running(self):
        assert StateVerifier._check_condition("service is running", None, "Service: active (running)")
        assert not StateVerifier._check_condition("service is running", None, "Service: stopped")


# ---------------------------------------------------------------------------
# FailureRecovery tests
# ---------------------------------------------------------------------------

class TestFailureRecovery:

    def _make_result(self, error: str, fc: FailureClass, retries: int = 2):
        return StepResult(
            step_id       = "s1",
            tool_name     = "test",
            parameters    = {},
            success       = False,
            error         = error,
            failure_class = fc,
            retry_count   = retries,
        )

    def test_hard_blocker_returns_blocked(self):
        rec    = FailureRecovery()
        step   = TaskStep(tool_name="test", max_retries=2)
        result = self._make_result("authorization required", FailureClass.HARD_BLOCKER)
        action = rec.handle(step, result, AgentTask(goal="test"), AgentState())
        assert action["action"] == "blocked"

    def test_transient_within_retries_returns_retry(self):
        rec    = FailureRecovery()
        step   = TaskStep(tool_name="test", max_retries=3)
        result = self._make_result("Connection timed out", FailureClass.TRANSIENT, retries=1)
        action = rec.handle(step, result, AgentTask(goal="test"), AgentState())
        assert action["action"] == "retry"

    def test_logical_failure_returns_replan(self):
        rec    = FailureRecovery()
        step   = TaskStep(tool_name="test", max_retries=2)
        result = self._make_result("invalid parameter", FailureClass.LOGICAL)
        action = rec.handle(step, result, AgentTask(goal="test"), AgentState())
        assert action["action"] == "replan"

    def test_environmental_returns_replan_or_continue(self):
        rec    = FailureRecovery()
        step   = TaskStep(tool_name="test", max_retries=2)
        result = self._make_result("command not found: nmap", FailureClass.ENVIRONMENTAL)
        action = rec.handle(step, result, AgentTask(goal="test"), AgentState())
        assert action["action"] in ("continue", "replan")


# ---------------------------------------------------------------------------
# AgentLoop integration test (fully mocked)
# ---------------------------------------------------------------------------

class TestAgentLoop:

    def _make_loop(self, tool_success=True, has_steps=True):
        # Planner mock
        planner = MagicMock()
        if has_steps:
            step = TaskStep(
                description = "ping localhost",
                tool_name   = "ping",
                parameters  = {"host": "127.0.0.1"},
                step_index  = 0,
            )
            planner.plan_steps = MagicMock(return_value=[step])
        else:
            planner.plan_steps = MagicMock(return_value=[])
        planner.replan_steps = MagicMock(return_value=[])

        # Executor mock
        executor_result = StepResult(
            step_id   = "s1",
            tool_name = "ping",
            parameters= {"host": "127.0.0.1"},
            success   = tool_success,
            raw_output= "reachable" if tool_success else None,
            error     = None if tool_success else "timeout",
            failure_class = None if tool_success else FailureClass.TRANSIENT,
        )
        executor = MagicMock()
        executor.execute = MagicMock(return_value=executor_result)

        # Verifier mock
        verifier = MagicMock()
        verifier.verify = MagicMock(return_value=(VerificationStatus.SKIPPED, "skipped"))

        # Recovery mock
        recovery = MagicMock()
        recovery.handle = MagicMock(return_value={"action": "skip", "detail": "test skip"})

        # Memory mock
        memory = MagicMock()
        memory.record = MagicMock()

        return AgentLoop(planner, executor, verifier, recovery, memory)

    def test_loop_completes_with_successful_step(self):
        loop  = self._make_loop(tool_success=True)
        task  = AgentTask(goal="Ping localhost")
        task.mark_started()
        state = AgentState()

        events = list(loop.run(task, state))
        types  = [e["type"] for e in events]

        assert "planning" in types
        assert "plan_ready" in types
        assert "step_start" in types
        assert "step_result" in types
        assert "loop_complete" in types

        # Task should be completed
        final = next(e for e in events if e["type"] == "loop_complete")
        assert final["status"] == "completed"

    def test_loop_with_no_steps_completes_immediately(self):
        loop  = self._make_loop(has_steps=False)
        task  = AgentTask(goal="Explain something")
        task.mark_started()
        state = AgentState()

        events = list(loop.run(task, state))
        types  = [e["type"] for e in events]

        assert "planning" in types
        assert "loop_complete" in types
        # No step_start should occur
        assert "step_start" not in types

    def test_loop_stop_requested(self):
        loop  = self._make_loop(tool_success=True)
        task  = AgentTask(goal="Test stop")
        task.mark_started()
        state = AgentState()
        state.stop_requested = True  # Pre-set stop

        events = list(loop.run(task, state))
        types  = [e["type"] for e in events]

        # Should detect stop before executing steps
        assert "cancelled" in types or "loop_complete" in types


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------

class TestHelpers:

    def test_summarize_none(self):
        assert _summarize_output(None) == "(no output)"

    def test_summarize_short_string(self):
        assert _summarize_output("hello world") == "hello world"

    def test_summarize_long_string(self):
        long = "\n".join([f"line {i}" for i in range(100)])
        summary = _summarize_output(long)
        assert "100 lines" in summary

    def test_summarize_dict(self):
        result = _summarize_output({"a": 1, "b": 2})
        assert "dict" in result

    def test_summarize_list(self):
        result = _summarize_output([1, 2, 3])
        assert "3" in result
