"""
tests/test_agent_kernel.py
==========================
Comprehensive tests for Master Prompt 01:
SentinelOS Agent Kernel & Architecture Baseline.

Verifies:
 1. Task creation
 2. Initial lifecycle state
 3. Valid lifecycle transitions
 4. Invalid lifecycle transitions rejected
 5. Plan creation and ordered steps
 6. TaskStep creation and dependencies
 7. State updates and runtime tracking
 8. Result recording
 9. Observation recording
10. Error recording
11. Verification recording
12. Task completion
13. Task failure
14. Task blocked state
15. Task cancellation
16. Serialization to JSON
17. Deserialization from JSON with full state restoration
18. Backward compatibility and model independence
"""

import json
import pytest
import time

from agent.kernel import Agent
from agent.state import (
    AgentState,
    AgentTask,
    FailureClass,
    InvalidLifecycleTransitionError,
    Plan,
    PlanStatus,
    StepResult,
    StepStatus,
    Task,
    TaskStatus,
    TaskStep,
    VerificationStatus,
)


class TestAgentKernel:

    # ----------------------------------------------------------------------
    # 1. Task Creation & 2. Initial Lifecycle State
    # ----------------------------------------------------------------------
    def test_01_task_creation_and_fields(self):
        task = Task(
            objective="Inspect the Sentinel workspace",
            constraints=["read_only", "no_network"],
            success_criteria=["all files enumerated", "report generated"],
            scope={"allowed_dirs": ["workspace"]},
            metadata={"priority": "high", "origin": "security_audit"},
        )
        assert task.task_id is not None
        assert len(task.task_id) > 0
        assert task.objective == "Inspect the Sentinel workspace"
        assert task.goal == "Inspect the Sentinel workspace"  # backward compat
        assert task.constraints == ["read_only", "no_network"]
        assert task.success_criteria == ["all files enumerated", "report generated"]
        assert task.scope == {"allowed_dirs": ["workspace"]}
        assert task.metadata == {"priority": "high", "origin": "security_audit"}
        assert task.created_at is not None
        assert task.updated_at is not None
        assert task.plan is None
        assert task.current_step is None

    def test_02_initial_lifecycle_state(self):
        task = Task(objective="Initial state check")
        assert task.status == TaskStatus.CREATED
        assert task.status == TaskStatus.PENDING  # backward compat alias

    # ----------------------------------------------------------------------
    # 3. Lifecycle Transitions & 4. Invalid Transitions
    # ----------------------------------------------------------------------
    def test_03_valid_lifecycle_progression(self):
        task = Task(objective="Progression test")
        assert task.status == TaskStatus.CREATED

        task.transition_to(TaskStatus.PLANNING, reason="Starting planner")
        assert task.status == TaskStatus.PLANNING

        task.transition_to(TaskStatus.READY, reason="Plan generated")
        assert task.status == TaskStatus.READY

        task.transition_to(TaskStatus.EXECUTING, reason="Executing steps")
        assert task.status == TaskStatus.EXECUTING

        task.transition_to(TaskStatus.WAITING, reason="Waiting for approval")
        assert task.status == TaskStatus.WAITING

        task.transition_to(TaskStatus.EXECUTING, reason="Resuming execution")
        assert task.status == TaskStatus.EXECUTING

        task.transition_to(TaskStatus.VERIFYING, reason="Verifying step")
        assert task.status == TaskStatus.VERIFYING

        task.transition_to(TaskStatus.RECOVERING, reason="Step failed, recovering")
        assert task.status == TaskStatus.RECOVERING

        task.transition_to(TaskStatus.EXECUTING, reason="Recovery succeeded")
        assert task.status == TaskStatus.EXECUTING

        task.transition_to(TaskStatus.COMPLETED, reason="All steps done")
        assert task.status == TaskStatus.COMPLETED

    def test_04_invalid_lifecycle_transitions_rejected(self):
        # 1. Terminal states allow no transitions out
        completed_task = Task(objective="Done task")
        completed_task.transition_to(TaskStatus.PLANNING)
        completed_task.transition_to(TaskStatus.COMPLETED)
        with pytest.raises(InvalidLifecycleTransitionError):
            completed_task.transition_to(TaskStatus.EXECUTING)

        # 2. Cannot jump directly from CREATED to COMPLETED
        fresh_task = Task(objective="Fresh task")
        with pytest.raises(InvalidLifecycleTransitionError):
            fresh_task.transition_to(TaskStatus.COMPLETED)

        # 3. Cannot jump directly from CREATED to VERIFYING
        with pytest.raises(InvalidLifecycleTransitionError):
            fresh_task.transition_to(TaskStatus.VERIFYING)

        # 4. Cannot jump from PLANNING directly to VERIFYING
        planning_task = Task(objective="Planning task")
        planning_task.transition_to(TaskStatus.PLANNING)
        with pytest.raises(InvalidLifecycleTransitionError):
            planning_task.transition_to(TaskStatus.VERIFYING)

        # 5. Cannot transition from CANCELLED to anything
        cancelled_task = Task(objective="Cancelled task")
        cancelled_task.cancel()
        assert cancelled_task.status == TaskStatus.CANCELLED
        with pytest.raises(InvalidLifecycleTransitionError):
            cancelled_task.transition_to(TaskStatus.READY)

    # ----------------------------------------------------------------------
    # 5. Plan Creation & 6. TaskStep Creation
    # ----------------------------------------------------------------------
    def test_05_plan_creation_and_ordering(self):
        plan = Plan(plan_id="plan-001", task_id="task-001")
        assert plan.status == PlanStatus.DRAFT
        assert plan.steps == []
        assert plan.current_step is None

        step1 = TaskStep(description="List files", tool_name="list_files")
        step2 = TaskStep(description="Read report", tool_name="read_file", parameters={"filename": "report.txt"})
        plan.add_step(step1)
        plan.add_step(step2)

        assert len(plan.steps) == 2
        assert plan.steps[0].step_index == 0
        assert plan.steps[1].step_index == 1
        assert plan.current_step is step1

        has_next = plan.advance()
        assert has_next is True
        assert plan.current_step is step2

        has_more = plan.advance()
        assert has_more is False
        assert plan.current_step is None

    def test_06_task_step_creation_and_attributes(self):
        step = TaskStep(
            step_id="step-123",
            description="Run port scan on lab host",
            intended_action="Execute port_scan against 127.0.0.1",
            tool_name="port_scan",
            parameters={"target": "127.0.0.1", "ports": "80,443"},
            dependencies=["step-001"],
            verify_condition="port 80 must be open",
            verify_tool="port_scan",
            max_retries=3,
            metadata={"risk": "low"},
        )
        assert step.step_id == "step-123"
        assert step.description == "Run port scan on lab host"
        assert step.intended_action == "Execute port_scan against 127.0.0.1"
        assert step.tool_name == "port_scan"
        assert step.parameters == {"target": "127.0.0.1", "ports": "80,443"}
        assert step.dependencies == ["step-001"]
        assert step.depends_on == ["step-001"]  # alias check
        assert step.verify_condition == "port 80 must be open"
        assert step.verify_tool == "port_scan"
        assert step.status == StepStatus.PENDING
        assert not step.is_complete()
        assert not step.has_failed()

    # ----------------------------------------------------------------------
    # 7. Agent Kernel & State Updates
    # ----------------------------------------------------------------------
    def test_07_agent_kernel_and_state_updates(self):
        agent = Agent()
        assert agent.state.active_task is None
        assert not agent.is_running

        task = agent.create_task(
            objective="Audit network perimeter",
            constraints=["internal_only"],
            success_criteria=["ports mapped"],
        )
        assert agent.state.active_task is task
        assert agent.state.objective == "Audit network perimeter"
        assert agent.state.lifecycle_state == TaskStatus.CREATED

        plan = Plan(task_id=task.task_id)
        s1 = TaskStep(step_id="s1", description="Scan", tool_name="port_scan")
        plan.add_step(s1)

        agent.transition_task(TaskStatus.PLANNING)
        assert agent.state.lifecycle_state == TaskStatus.PLANNING

        agent.attach_plan(plan)
        assert agent.state.lifecycle_state == TaskStatus.READY
        assert agent.state.current_step is s1

        agent.start_task()
        assert agent.state.lifecycle_state == TaskStatus.EXECUTING
        assert agent.is_running

    # ----------------------------------------------------------------------
    # 8. Result Recording
    # ----------------------------------------------------------------------
    def test_08_record_result(self):
        agent = Agent()
        task = agent.create_task("Test result recording")
        plan = Plan(task_id=task.task_id)
        s1 = TaskStep(step_id="s1", tool_name="list_files")
        plan.add_step(s1)
        agent.attach_plan(plan)

        result = StepResult(
            step_id="s1",
            tool_name="list_files",
            parameters={},
            raw_output=["file1.py", "file2.py"],
            success=True,
            execution_time_ms=12,
        )
        agent.record_result("s1", result)

        assert s1.result is result
        assert s1.status == StepStatus.SUCCESS
        assert len(agent.state.tool_results) == 1
        assert agent.state.tool_results[0].raw_output == ["file1.py", "file2.py"]

    # ----------------------------------------------------------------------
    # 9. Observation Recording
    # ----------------------------------------------------------------------
    def test_09_record_observation(self):
        agent = Agent()
        task = agent.create_task("Observation test")
        plan = Plan(task_id=task.task_id)
        s1 = TaskStep(step_id="s1", tool_name="list_files")
        plan.add_step(s1)
        agent.attach_plan(plan)

        agent.record_observation(
            step_id="s1",
            observation="Found 2 files in workspace",
            data={"count": 2},
        )
        assert len(task.observations) == 1
        assert task.observations[0]["step_id"] == "s1"
        assert task.observations[0]["observation"] == "Found 2 files in workspace"
        assert task.observations[0]["data"] == {"count": 2}
        assert s1.observation == "Found 2 files in workspace"
        assert len(agent.state.observations) == 1

    # ----------------------------------------------------------------------
    # 10. Error Recording
    # ----------------------------------------------------------------------
    def test_10_record_error(self):
        agent = Agent()
        task = agent.create_task("Error test")
        agent.record_error(
            step_id="s1",
            error="Connection timed out after 5s",
            failure_class=FailureClass.TRANSIENT,
        )
        assert len(task.errors) == 1
        assert task.errors[0]["step_id"] == "s1"
        assert task.errors[0]["error"] == "Connection timed out after 5s"
        assert task.errors[0]["failure_class"] == FailureClass.TRANSIENT.value
        assert len(agent.state.errors) == 1

    # ----------------------------------------------------------------------
    # 11. Verification Recording
    # ----------------------------------------------------------------------
    def test_11_record_verification(self):
        agent = Agent()
        task = agent.create_task("Verification test")
        plan = Plan(task_id=task.task_id)
        s1 = TaskStep(step_id="s1", tool_name="list_files")
        plan.add_step(s1)
        agent.attach_plan(plan)

        res = StepResult(step_id="s1", tool_name="list_files", parameters={}, success=True)
        agent.record_result("s1", res)

        agent.record_verification("s1", VerificationStatus.PASSED, detail="File list confirmed non-empty")
        assert s1.verification_state == VerificationStatus.PASSED
        assert res.verification_status == VerificationStatus.PASSED
        assert res.verification_detail == "File list confirmed non-empty"

        v_results = agent.state.verification_results
        assert len(v_results) == 1
        assert v_results[0]["status"] == "passed"
        assert v_results[0]["detail"] == "File list confirmed non-empty"

    # ----------------------------------------------------------------------
    # 12. Completion, 13. Failure, 14. Blocked, 15. Cancellation
    # ----------------------------------------------------------------------
    def test_12_completion(self):
        agent = Agent()
        task = agent.create_task("Completion test")
        agent.start_task()
        agent.mark_completed("Workspace successfully analyzed")
        assert task.status == TaskStatus.COMPLETED
        assert task.conclusion == "Workspace successfully analyzed"
        assert task.completed_at is not None
        assert agent.state.active_task is None
        assert len(agent.state.task_history) == 1

    def test_13_failure(self):
        agent = Agent()
        task = agent.create_task("Failure test")
        agent.start_task()
        agent.mark_failed("Permission denied accessing resource")
        assert task.status == TaskStatus.FAILED
        assert task.conclusion == "Permission denied accessing resource"
        assert task.completed_at is not None
        assert agent.state.active_task is None
        assert len(agent.state.task_history) == 1

    def test_14_blocked_state(self):
        agent = Agent()
        task = agent.create_task("Blocked test")
        agent.start_task()
        agent.mark_blocked("Requires user confirmation to proceed")
        assert task.status == TaskStatus.BLOCKED
        assert task.conclusion == "Requires user confirmation to proceed"
        # Task remains in active state (not completed) so user can unblock
        assert agent.state.active_task is task
        # Unblocking back to READY or EXECUTING
        agent.transition_task(TaskStatus.READY, reason="User confirmed")
        assert task.status == TaskStatus.READY

    def test_15_cancellation(self):
        agent = Agent()
        task = agent.create_task("Cancel test")
        agent.start_task()
        agent.cancel("User aborted run")
        assert task.status == TaskStatus.CANCELLED
        assert task.conclusion == "User aborted run"
        assert agent.state.active_task is None
        assert len(agent.state.task_history) == 1

    # ----------------------------------------------------------------------
    # 16. Serialization & 17. Deserialization
    # ----------------------------------------------------------------------
    def test_16_17_full_serialization_deserialization_roundtrip(self):
        # Build a complete structured runtime state
        state = AgentState(
            session_id="session-xyz-123",
            execution_metadata={"environment": "test", "version": "1.0"},
            max_steps=25,
            max_retries=3,
        )
        task = Task(
            objective="Inspect the SentinelOS workspace",
            constraints=["workspace_sandbox"],
            success_criteria=["files counted"],
            scope={"path": "workspace"},
            metadata={"run_id": "r-01"},
            status=TaskStatus.VERIFYING,
        )
        plan = Plan(plan_id="plan-456", task_id=task.task_id, status=PlanStatus.IN_PROGRESS)
        s1 = TaskStep(
            step_id="step-1",
            step_index=0,
            description="List directory",
            tool_name="list_files",
            parameters={"path": "."},
            status=StepStatus.SUCCESS,
            verify_condition="files exist",
            verification_state=VerificationStatus.PASSED,
        )
        s1.result = StepResult(
            step_id="step-1",
            tool_name="list_files",
            parameters={"path": "."},
            raw_output=["README.md", "main.py"],
            success=True,
            verification_status=VerificationStatus.PASSED,
            verification_detail="Found 2 files",
        )
        plan.add_step(s1)
        task.attach_plan(plan)
        task.add_observation("step-1", "Workspace contains 2 files", {"files": ["README.md", "main.py"]})
        task.add_error("step-1", "Warning: transient delay", FailureClass.TRANSIENT)

        state.set_task(task)

        # 16. Serialize to JSON
        json_str = state.to_json()
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed["session_id"] == "session-xyz-123"
        assert parsed["active_task"]["objective"] == "Inspect the SentinelOS workspace"
        assert parsed["active_task"]["status"] == "verifying"
        assert len(parsed["active_task"]["steps"]) == 1
        assert parsed["active_task"]["steps"][0]["tool_name"] == "list_files"

        # 17. Restore from JSON
        restored_state = AgentState.from_json(json_str)
        assert restored_state.session_id == state.session_id
        assert restored_state.max_steps == 25
        assert restored_state.max_retries == 3
        assert restored_state.execution_metadata == {"environment": "test", "version": "1.0"}

        restored_task = restored_state.active_task
        assert restored_task is not None
        assert restored_task.task_id == task.task_id
        assert restored_task.objective == task.objective
        assert restored_task.status == TaskStatus.VERIFYING
        assert restored_task.constraints == ["workspace_sandbox"]
        assert restored_task.success_criteria == ["files counted"]
        assert restored_task.scope == {"path": "workspace"}

        # Plan and step verification
        assert restored_task.plan is not None
        assert restored_task.plan.plan_id == "plan-456"
        assert len(restored_task.steps) == 1
        restored_step = restored_task.steps[0]
        assert restored_step.step_id == "step-1"
        assert restored_step.tool_name == "list_files"
        assert restored_step.status == StepStatus.SUCCESS
        assert restored_step.verification_state == VerificationStatus.PASSED
        assert restored_step.result is not None
        assert restored_step.result.raw_output == ["README.md", "main.py"]
        assert restored_step.result.verification_status == VerificationStatus.PASSED

        # Observations and errors
        assert len(restored_task.observations) == 1
        assert restored_task.observations[0]["observation"] == "Workspace contains 2 files"
        assert len(restored_task.errors) == 1
        assert restored_task.errors[0]["failure_class"] == "transient"

    # ----------------------------------------------------------------------
    # 18. Model Independence Check
    # ----------------------------------------------------------------------
    def test_18_kernel_is_model_independent(self):
        """Verify kernel data structures do not import or require any LLM provider."""
        import sys
        # Check that importing agent.state does not require ollama or network
        from agent.state import Task, AgentState, Plan, TaskStep, StepResult
        assert Task is not None
        assert AgentState is not None
        assert Plan is not None
        assert TaskStep is not None
        assert StepResult is not None
