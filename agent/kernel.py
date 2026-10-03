"""
agent/kernel.py
===============
Clean Agent abstraction for the SentinelOS agent runtime.

Coordinates task state, plan execution state, and lifecycle progression
WITHOUT coupling to LLM reasoning, tool implementations, UI, or persistent storage.
"""

from __future__ import annotations

import time
from typing import Any

from core.logger import logger
from agent.state import (
    AgentState,
    AgentTask,
    FailureClass,
    Plan,
    StepResult,
    StepStatus,
    Task,
    TaskStatus,
    TaskStep,
    VerificationStatus,
)


class Agent:
    """
    SentinelOS Agent Kernel.
    
    Coordinates:
    - Task creation and initialization
    - Lifecycle state changes and enforcement
    - Execution plan attachment and step advancement
    - Observation, result, error, and verification recording
    - Completion, failure, blocking, and cancellation tracking
    
    Model-independent and runtime-isolated:
    Does NOT call models, execute tools directly, or render UI.
    """

    def __init__(self, state: AgentState | None = None) -> None:
        self._state = state or AgentState()

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def active_task(self) -> Task | None:
        return self._state.active_task

    @property
    def is_running(self) -> bool:
        return self._state.is_running

    # ------------------------------------------------------------------
    # Task Management
    # ------------------------------------------------------------------

    def create_task(
        self,
        objective: str = "",
        goal: str = "",
        constraints: list[str] | None = None,
        success_criteria: list[str] | None = None,
        scope: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        mode: str = "chat",
    ) -> Task:
        """Create a new Task and set it as active in AgentState."""
        task = Task(
            objective        = objective or goal,
            constraints      = constraints,
            success_criteria = success_criteria,
            scope            = scope,
            metadata         = metadata,
            context          = context,
            mode             = mode,
            status           = TaskStatus.CREATED,
        )
        self._state.set_task(task)
        logger.info(f"Agent: created task [{task.task_id[:8]}] objective='{task.objective[:80]}'")
        return task

    def start_task(self, task: Task | None = None) -> None:
        """Start the task, marking started timestamp and moving into EXECUTING."""
        target_task = task or self._state.active_task
        if target_task is None:
            raise ValueError("No active task to start.")
        if target_task is not self._state.active_task:
            self._state.set_task(target_task)

        target_task.mark_started()
        logger.info(f"Agent: started task [{target_task.task_id[:8]}]")

    def inspect_task(self) -> dict[str, Any] | None:
        """Inspect the current active task state."""
        if self._state.active_task is None:
            return None
        return self._state.active_task.to_dict()

    # ------------------------------------------------------------------
    # Lifecycle Management
    # ------------------------------------------------------------------

    def transition_task(self, target_status: TaskStatus | str, reason: str | None = None) -> None:
        """Transition active task to target lifecycle state."""
        if self._state.active_task is None:
            raise ValueError("No active task to transition.")
        self._state.active_task.transition_to(target_status, reason=reason)

    def attach_plan(self, plan: Plan) -> None:
        """Attach an execution plan to the active task."""
        if self._state.active_task is None:
            raise ValueError("No active task to attach plan to.")
        self._state.active_task.attach_plan(plan)
        logger.info(f"Agent: attached plan [{plan.plan_id}] to task [{self._state.active_task.task_id[:8]}]")

    def set_current_step(self, step_index: int) -> None:
        """Update current step index."""
        if self._state.active_task is None:
            raise ValueError("No active task.")
        self._state.active_task.current_step_index = step_index
        logger.info(f"Agent: set current step to [{step_index}] for task [{self._state.active_task.task_id[:8]}]")

    def advance_step(self) -> bool:
        """Advance to next step in task plan. Returns True if next step exists."""
        if self._state.active_task is None:
            raise ValueError("No active task to advance.")
        has_next = self._state.active_task.advance()
        logger.info(
            f"Agent: advanced task [{self._state.active_task.task_id[:8]}] "
            f"to step [{self._state.active_task.current_step_index}] (has_next={has_next})"
        )
        return has_next

    # ------------------------------------------------------------------
    # Recording Observations, Results, Errors, Verifications
    # ------------------------------------------------------------------

    def record_result(self, step_id: str, result: StepResult) -> None:
        """Record a tool execution result for a step."""
        if self._state.active_task is None:
            raise ValueError("No active task.")
        step = self._find_step(step_id)
        if step:
            step.result = result
            step.status = StepStatus.SUCCESS if result.success else StepStatus.FAILED
        logger.info(
            f"Agent: recorded result for step [{step_id}] on task [{self._state.active_task.task_id[:8]}]: "
            f"tool='{result.tool_name}' success={result.success}"
        )

    def record_observation(self, step_id: str, observation: str, data: Any = None) -> None:
        """Record an observation derived from tool output or state inspection."""
        if self._state.active_task is None:
            raise ValueError("No active task.")
        self._state.active_task.add_observation(step_id=step_id, observation=observation, data=data)
        step = self._find_step(step_id)
        if step:
            step.observation = observation
        logger.info(f"Agent: recorded observation for step [{step_id}]: {observation[:80]}")

    def record_error(
        self,
        step_id: str,
        error: str,
        failure_class: FailureClass | None = None,
    ) -> None:
        """Record an error for a step."""
        if self._state.active_task is None:
            raise ValueError("No active task.")
        self._state.active_task.add_error(step_id=step_id, error=error, failure_class=failure_class)
        logger.warning(f"Agent: recorded error for step [{step_id}]: {error[:80]}")

    def record_verification(
        self,
        step_id: str,
        status: VerificationStatus | str,
        detail: str | None = None,
    ) -> None:
        """Record post-execution verification outcome for a step."""
        if self._state.active_task is None:
            raise ValueError("No active task.")
        v_status = VerificationStatus(status) if isinstance(status, str) else status
        step = self._find_step(step_id)
        if step:
            step.verification_state = v_status
            if step.result:
                step.result.verification_status = v_status
                step.result.verification_detail = detail
        logger.info(f"Agent: recorded verification for step [{step_id}]: status={v_status.value} detail={detail}")

    # ------------------------------------------------------------------
    # Terminal & Exception State Transitions
    # ------------------------------------------------------------------

    def mark_completed(self, conclusion: str = "") -> None:
        """Mark the active task as successfully completed."""
        if self._state.active_task is None:
            raise ValueError("No active task.")
        task = self._state.active_task
        task.mark_completed(conclusion=conclusion)
        self._state.complete_task()
        logger.info(f"Agent: task [{task.task_id[:8]}] completed: {conclusion[:80]}")

    def mark_failed(self, reason: str = "") -> None:
        """Mark the active task as failed."""
        if self._state.active_task is None:
            raise ValueError("No active task.")
        task = self._state.active_task
        task.mark_failed(reason=reason)
        self._state.complete_task()
        logger.error(f"Agent: task [{task.task_id[:8]}] failed: {reason[:80]}")

    def mark_blocked(self, reason: str = "") -> None:
        """Mark the active task as blocked (e.g. pending authorization or input)."""
        if self._state.active_task is None:
            raise ValueError("No active task.")
        self._state.active_task.mark_blocked(reason=reason)
        logger.warning(f"Agent: task [{self._state.active_task.task_id[:8]}] blocked: {reason[:80]}")

    def cancel(self, reason: str = "") -> None:
        """Cancel task execution."""
        if self._state.active_task is None:
            raise ValueError("No active task.")
        task = self._state.active_task
        task.cancel(reason=reason)
        self._state.complete_task()
        logger.info(f"Agent: task [{task.task_id[:8]}] cancelled: {reason[:80]}")

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _find_step(self, step_id: str) -> TaskStep | None:
        if not self._state.active_task or not self._state.active_task.steps:
            return None
        for step in self._state.active_task.steps:
            if step.step_id == step_id:
                return step
        return None
