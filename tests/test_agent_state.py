"""
tests/test_agent_state.py
=========================
Tests for the agent state model (agent/state.py).

Validates:
- Task/step creation and lifecycle transitions
- StepResult construction
- AgentState session management
- Task summary and dict serialization
"""

import pytest
import time

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


# ---------------------------------------------------------------------------
# AgentTask
# ---------------------------------------------------------------------------

class TestAgentTask:

    def test_create_task(self):
        task = AgentTask(goal="Test goal")
        assert task.task_id
        assert task.goal == "Test goal"
        assert task.status == TaskStatus.PENDING
        assert task.steps == []
        assert task.observations == []

    def test_mark_started(self):
        task = AgentTask(goal="Test")
        task.mark_started()
        assert task.started_at is not None
        assert task.status == TaskStatus.RUNNING

    def test_mark_completed(self):
        task = AgentTask(goal="Test")
        task.mark_started()
        task.mark_completed("All done")
        assert task.status == TaskStatus.COMPLETED
        assert task.conclusion == "All done"
        assert task.completed_at is not None

    def test_mark_failed(self):
        task = AgentTask(goal="Test")
        task.mark_failed("Something broke")
        assert task.status == TaskStatus.FAILED
        assert "broke" in task.conclusion

    def test_mark_blocked(self):
        task = AgentTask(goal="Test")
        task.mark_blocked("Need credentials")
        assert task.status == TaskStatus.BLOCKED

    def test_current_step_none_when_no_steps(self):
        task = AgentTask(goal="Test")
        assert task.current_step is None

    def test_current_step_returns_correct_step(self):
        task = AgentTask(goal="Test")
        s1   = TaskStep(description="Step 1", tool_name="ping")
        s2   = TaskStep(description="Step 2", tool_name="dns_lookup")
        task.steps = [s1, s2]
        assert task.current_step is s1
        task.advance()
        assert task.current_step is s2

    def test_advance_returns_false_at_end(self):
        task = AgentTask(goal="Test")
        task.steps = [TaskStep(tool_name="ping")]
        assert task.advance() is False

    def test_advance_returns_true_when_more_steps(self):
        task = AgentTask(goal="Test")
        task.steps = [TaskStep(tool_name="ping"), TaskStep(tool_name="dns_lookup")]
        assert task.advance() is True

    def test_add_observation(self):
        task = AgentTask(goal="Test")
        task.add_observation("step1", "Found open port 22", {"port": 22})
        assert len(task.observations) == 1
        assert task.observations[0]["observation"] == "Found open port 22"

    def test_add_error(self):
        task = AgentTask(goal="Test")
        task.add_error("step1", "Permission denied", FailureClass.ENVIRONMENTAL)
        assert len(task.errors) == 1
        assert "Permission denied" in task.errors[0]["error"]

    def test_completed_steps_filtered(self):
        task = AgentTask(goal="Test")
        s1 = TaskStep(tool_name="ping")
        s2 = TaskStep(tool_name="dns_lookup")
        s1.status = StepStatus.SUCCESS
        s2.status = StepStatus.PENDING
        task.steps = [s1, s2]
        assert s1 in task.completed_steps
        assert s2 not in task.completed_steps

    def test_failed_steps_filtered(self):
        task = AgentTask(goal="Test")
        s1 = TaskStep(tool_name="ping")
        s2 = TaskStep(tool_name="dns_lookup")
        s1.status = StepStatus.FAILED
        s2.status = StepStatus.SUCCESS
        task.steps = [s1, s2]
        assert s1 in task.failed_steps
        assert s2 not in task.failed_steps

    def test_elapsed_seconds(self):
        task = AgentTask(goal="Test")
        task.mark_started()
        time.sleep(0.05)
        task.mark_completed("done")
        assert task.elapsed_seconds >= 0.05

    def test_to_dict_shape(self):
        task = AgentTask(goal="Test goal")
        d    = task.to_dict()
        assert "task_id" in d
        assert "goal" in d
        assert "status" in d
        assert "steps" in d

    def test_summary_string(self):
        task = AgentTask(goal="Test")
        task.mark_started()
        s = task.summary()
        assert "RUNNING" in s.upper()


# ---------------------------------------------------------------------------
# TaskStep
# ---------------------------------------------------------------------------

class TestTaskStep:

    def test_step_defaults(self):
        step = TaskStep(tool_name="ping")
        assert step.status == StepStatus.PENDING
        assert step.result is None
        assert step.max_retries == 2

    def test_is_complete_success(self):
        step = TaskStep(tool_name="ping")
        step.status = StepStatus.SUCCESS
        assert step.is_complete()

    def test_is_complete_skipped(self):
        step = TaskStep(tool_name="ping")
        step.status = StepStatus.SKIPPED
        assert step.is_complete()

    def test_has_failed(self):
        step = TaskStep(tool_name="ping")
        step.status = StepStatus.FAILED
        assert step.has_failed()
        assert not step.is_complete()

    def test_to_dict(self):
        step = TaskStep(description="Ping host", tool_name="ping", parameters={"host": "127.0.0.1"})
        d    = step.to_dict()
        assert d["tool_name"] == "ping"
        assert d["description"] == "Ping host"


# ---------------------------------------------------------------------------
# StepResult
# ---------------------------------------------------------------------------

class TestStepResult:

    def test_result_success(self):
        r = StepResult(
            step_id    = "abc",
            tool_name  = "ping",
            parameters = {"host": "127.0.0.1"},
            success    = True,
            raw_output = {"reachable": True},
        )
        assert r.success
        assert r.verification_status == VerificationStatus.NOT_RUN

    def test_result_failure(self):
        r = StepResult(
            step_id       = "abc",
            tool_name     = "ping",
            parameters    = {},
            success       = False,
            error         = "Timeout",
            failure_class = FailureClass.TRANSIENT,
        )
        assert not r.success
        assert r.failure_class == FailureClass.TRANSIENT

    def test_to_dict(self):
        r = StepResult(
            step_id   = "abc",
            tool_name = "ping",
            parameters= {},
        )
        d = r.to_dict()
        assert "step_id" in d
        assert "verification_status" in d


# ---------------------------------------------------------------------------
# AgentState
# ---------------------------------------------------------------------------

class TestAgentState:

    def test_initial_state(self):
        state = AgentState()
        assert state.active_task is None
        assert not state.is_running
        assert state.stop_requested is False

    def test_set_task(self):
        state = AgentState()
        task  = AgentTask(goal="Test")
        task.mark_started()
        task.status = TaskStatus.RUNNING
        state.set_task(task)
        assert state.active_task is task
        assert state.is_running

    def test_request_stop(self):
        state = AgentState()
        task  = AgentTask(goal="Test")
        task.mark_started()
        task.status = TaskStatus.RUNNING
        state.set_task(task)
        state.request_stop()
        assert state.stop_requested
        assert task.status == TaskStatus.CANCELLED

    def test_complete_task_moves_to_history(self):
        state = AgentState()
        task  = AgentTask(goal="Test")
        state.set_task(task)
        state.complete_task()
        assert state.active_task is None
        assert len(state.task_history) == 1

    def test_to_dict(self):
        state = AgentState()
        d     = state.to_dict()
        assert "session_id" in d
        assert "is_running" in d
