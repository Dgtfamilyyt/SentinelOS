"""
scripts/smoke_test_mp1.py
=========================
Master Prompt 01 Smoke Test:
Demonstrates a harmless task representation and full structured lifecycle progression:
CREATED -> PLANNING -> READY -> EXECUTING -> VERIFYING -> COMPLETED
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.kernel import Agent
from agent.state import (
    Plan,
    PlanStatus,
    StepResult,
    StepStatus,
    TaskStatus,
    TaskStep,
    VerificationStatus,
)


def run_smoke_test():
    print("=" * 60)
    print("SentinelOS Agent Kernel — Master Prompt 01 Smoke Test")
    print("=" * 60)

    # 1. Initialize Agent Kernel
    agent = Agent()
    print("\n[1] Agent initialized. Active task:", agent.active_task)

    # 2. Create Task (CREATED)
    objective = "Inspect the current SentinelOS workspace."
    task = agent.create_task(
        objective=objective,
        constraints=["workspace_sandbox_only", "read_only"],
        success_criteria=["workspace files enumerated", "state verified"],
        scope={"target_path": "."},
        metadata={"source": "mp1_smoke_test"},
    )
    print(f"\n[2] Task Created: [{task.task_id[:8]}]")
    print(f"    Objective: {task.objective}")
    print(f"    Lifecycle State: {task.status.value.upper()}")
    assert task.status == TaskStatus.CREATED

    # 3. Transition to PLANNING
    agent.transition_task(TaskStatus.PLANNING, reason="Decomposing objective into steps")
    print(f"\n[3] Lifecycle Transition: {task.status.value.upper()}")
    assert task.status == TaskStatus.PLANNING

    # 4. Attach Plan (READY)
    plan = Plan(task_id=task.task_id, status=PlanStatus.READY)
    step1 = TaskStep(
        step_id="step-01",
        step_index=0,
        description="Enumerate workspace files",
        intended_action="Call list_files tool on workspace root",
        tool_name="list_files",
        parameters={"path": "."},
        verify_condition="File listing must return a non-empty list",
    )
    plan.add_step(step1)
    agent.attach_plan(plan)
    print(f"\n[4] Plan Attached: [{plan.plan_id}] with {len(plan.steps)} step(s)")
    print(f"    Lifecycle State: {task.status.value.upper()}")
    assert task.status == TaskStatus.READY

    # 5. Start Execution (EXECUTING)
    agent.start_task()
    print(f"\n[5] Task Started: {task.status.value.upper()}")
    print(f"    Current Step: [{agent.state.current_step.step_id}] {agent.state.current_step.description}")
    assert task.status == TaskStatus.EXECUTING

    # 6. Record Tool Execution Result
    result = StepResult(
        step_id=step1.step_id,
        tool_name="list_files",
        parameters={"path": "."},
        raw_output=["README.md", "main.py", "config", "core", "agent"],
        success=True,
        execution_time_ms=5,
    )
    agent.record_result(step1.step_id, result)
    print(f"\n[6] Step Result Recorded:")
    print(f"    Tool: {result.tool_name} | Success: {result.success} | Execution Time: {result.execution_time_ms}ms")
    print(f"    Output: {result.raw_output}")

    # 7. Record Observation
    obs_text = "Workspace root contains README.md, main.py, config, core, agent."
    agent.record_observation(step1.step_id, observation=obs_text, data={"file_count": 5})
    print(f"\n[7] Observation Recorded:")
    print(f"    Observation: {obs_text}")

    # 8. Transition to VERIFYING & Record Verification
    agent.transition_task(TaskStatus.VERIFYING, reason="Verifying step outcome matches condition")
    print(f"\n[8] Lifecycle Transition: {task.status.value.upper()}")
    assert task.status == TaskStatus.VERIFYING

    agent.record_verification(
        step_id=step1.step_id,
        status=VerificationStatus.PASSED,
        detail="Workspace files confirmed non-empty (5 items found).",
    )
    print(f"    Verification Recorded: PASSED (Workspace files confirmed non-empty).")

    # 9. Mark Completed (COMPLETED)
    conclusion = "SentinelOS workspace inspected successfully. 5 files/directories present."
    agent.mark_completed(conclusion=conclusion)
    print(f"\n[9] Task Completed:")
    print(f"    Lifecycle State: {task.status.value.upper()}")
    print(f"    Conclusion: {task.conclusion}")
    assert task.status == TaskStatus.COMPLETED

    # 10. Verify Serialization Roundtrip
    print("\n[10] Testing Full Serialization & Restoration:")
    json_state = agent.state.to_json()
    print(f"    Serialized JSON length: {len(json_state)} bytes")

    restored_state = agent.state.from_json(json_state)
    assert len(restored_state.task_history) == 1
    restored_task = restored_state.task_history[0]
    assert restored_task.task_id == task.task_id
    assert restored_task.objective == task.objective
    assert restored_task.status == TaskStatus.COMPLETED
    assert restored_task.conclusion == conclusion
    assert len(restored_task.observations) == 1
    assert restored_task.steps[0].result.success is True
    assert restored_task.steps[0].verification_state == VerificationStatus.PASSED
    print("    Restoration: SUCCESS. State restored with 100% fidelity.")

    print("\n" + "=" * 60)
    print("SMOKE TEST COMPLETE: All assertions passed successfully.")
    print("=" * 60)
    return True


if __name__ == "__main__":
    run_smoke_test()
