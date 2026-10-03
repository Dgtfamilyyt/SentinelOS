"""
agent/state.py
==============
Core data model for Sentinel's agentic execution layer.

This module provides the structured runtime foundation for SentinelOS agents:
- Lifecycle enumerations and strict transition rules
- StepResult, TaskStep, and Plan representations
- Task / AgentTask model with full lifecycle tracking
- AgentState runtime session container
- Serialization and deserialization (JSON-compatible)

Model-independent: contains ZERO LLM calls, prompts, or provider logic.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.logger import logger


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class TaskStatus(str, Enum):
    """
    Explicit lifecycle states for an Agent Task.
    
    Progression model:
    CREATED -> PLANNING -> READY -> EXECUTING -> [WAITING / VERIFYING / RECOVERING] -> COMPLETED
    Terminal states: COMPLETED, FAILED, CANCELLED
    Interrupted/Hold state: BLOCKED
    """
    CREATED    = "created"
    PLANNING   = "planning"
    READY      = "ready"
    EXECUTING  = "executing"
    WAITING    = "waiting"
    VERIFYING  = "verifying"
    RECOVERING = "recovering"
    COMPLETED  = "completed"
    FAILED     = "failed"
    BLOCKED    = "blocked"
    CANCELLED  = "cancelled"

    @classmethod
    def _missing_(cls, value: object) -> Any:
        if isinstance(value, str):
            v = value.strip().lower()
            if v == "pending":
                return cls.CREATED
            if v == "running":
                return cls.EXECUTING
        return super()._missing_(value)


# Backward compatibility aliases
TaskStatus.PENDING = TaskStatus.CREATED  # type: ignore[attr-defined]
TaskStatus.RUNNING = TaskStatus.EXECUTING  # type: ignore[attr-defined]


class StepStatus(str, Enum):
    """Status of an individual TaskStep."""
    PENDING   = "pending"
    RUNNING   = "running"
    SUCCESS   = "success"
    FAILED    = "failed"
    SKIPPED   = "skipped"
    RETRYING  = "retrying"


class PlanStatus(str, Enum):
    """Lifecycle status of a structured execution Plan."""
    DRAFT       = "draft"
    READY       = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    FAILED      = "failed"
    CANCELLED   = "cancelled"


class FailureClass(str, Enum):
    """
    Failure classification used by recovery handling.
    """
    TRANSIENT     = "transient"      # Timeout, network blip — retry is safe
    ENVIRONMENTAL = "environmental"  # Tool missing, permission denied — needs environment fix
    LOGICAL       = "logical"        # Wrong parameters, bad approach — replan needed
    HARD_BLOCKER  = "hard_blocker"   # Requires human authorization or external input


class VerificationStatus(str, Enum):
    """Outcome of post-execution verification."""
    NOT_RUN = "not_run"
    PASSED  = "passed"
    FAILED  = "failed"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# Lifecycle Transition Rules
# ---------------------------------------------------------------------------

class InvalidLifecycleTransitionError(ValueError):
    """Raised when an illegal lifecycle transition is attempted."""
    def __init__(
        self,
        current_status: TaskStatus,
        target_status: TaskStatus,
        task_id: str = "",
        reason: str = "",
    ):
        self.current_status = current_status
        self.target_status = target_status
        self.task_id = task_id
        self.reason = reason
        msg = f"Invalid lifecycle transition from '{current_status.value}' to '{target_status.value}'"
        if task_id:
            msg += f" for task {task_id[:8]}"
        if reason:
            msg += f" (reason: {reason})"
        super().__init__(msg)


# Centralized permitted transitions
VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.CREATED: {
        TaskStatus.PLANNING,
        TaskStatus.READY,
        TaskStatus.EXECUTING,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
    },
    TaskStatus.PLANNING: {
        TaskStatus.READY,
        TaskStatus.EXECUTING,
        TaskStatus.COMPLETED,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
    },
    TaskStatus.READY: {
        TaskStatus.EXECUTING,
        TaskStatus.PLANNING,
        TaskStatus.COMPLETED,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
    },
    TaskStatus.EXECUTING: {
        TaskStatus.WAITING,
        TaskStatus.VERIFYING,
        TaskStatus.RECOVERING,
        TaskStatus.PLANNING,
        TaskStatus.READY,
        TaskStatus.COMPLETED,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
    },
    TaskStatus.WAITING: {
        TaskStatus.EXECUTING,
        TaskStatus.READY,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
    },
    TaskStatus.VERIFYING: {
        TaskStatus.EXECUTING,
        TaskStatus.READY,
        TaskStatus.RECOVERING,
        TaskStatus.PLANNING,
        TaskStatus.COMPLETED,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
    },
    TaskStatus.RECOVERING: {
        TaskStatus.EXECUTING,
        TaskStatus.PLANNING,
        TaskStatus.READY,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
    },
    TaskStatus.BLOCKED: {
        TaskStatus.READY,
        TaskStatus.PLANNING,
        TaskStatus.EXECUTING,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
    },
    # Terminal states allow no outgoing transitions
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}


def validate_lifecycle_transition(
    current: TaskStatus,
    target: TaskStatus,
    task_id: str = "",
    reason: str = "",
) -> None:
    """Enforces centralized lifecycle transition rules."""
    if current == target:
        return
    allowed = VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidLifecycleTransitionError(
            current_status=current,
            target_status=target,
            task_id=task_id,
            reason=reason,
        )


# ---------------------------------------------------------------------------
# Step Result
# ---------------------------------------------------------------------------

@dataclass
class StepResult:
    """
    The complete output and verification outcome of an executed TaskStep.
    """
    step_id:              str
    tool_name:            str
    parameters:           dict[str, Any]
    raw_output:           Any                        = None
    success:              bool                       = False
    error:                str | None                 = None
    failure_class:        FailureClass | None        = None
    verification_status:  VerificationStatus         = VerificationStatus.NOT_RUN
    verification_detail:  str | None                 = None
    retry_count:          int                        = 0
    execution_time_ms:    int                        = 0
    timestamp:            float                      = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id":             self.step_id,
            "tool_name":           self.tool_name,
            "parameters":          self.parameters,
            "raw_output":          self.raw_output,
            "success":             self.success,
            "error":               self.error,
            "failure_class":       self.failure_class.value if self.failure_class else None,
            "verification_status": self.verification_status.value,
            "verification_detail": self.verification_detail,
            "retry_count":         self.retry_count,
            "execution_time_ms":   self.execution_time_ms,
            "timestamp":           self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StepResult:
        fc = data.get("failure_class")
        vs = data.get("verification_status")
        return cls(
            step_id             = data.get("step_id", ""),
            tool_name           = data.get("tool_name", ""),
            parameters          = data.get("parameters", {}),
            raw_output          = data.get("raw_output"),
            success             = bool(data.get("success", False)),
            error               = data.get("error"),
            failure_class       = FailureClass(fc) if fc else None,
            verification_status = VerificationStatus(vs) if vs else VerificationStatus.NOT_RUN,
            verification_detail = data.get("verification_detail"),
            retry_count         = int(data.get("retry_count", 0)),
            execution_time_ms   = int(data.get("execution_time_ms", 0)),
            timestamp           = float(data.get("timestamp", time.time())),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> StepResult:
        return cls.from_dict(json.loads(json_str))


# ---------------------------------------------------------------------------
# Task Step
# ---------------------------------------------------------------------------

@dataclass
class TaskStep:
    """
    A single planned action within an execution Plan.
    """
    step_id:            str                 = field(default_factory=lambda: str(uuid.uuid4())[:8])
    step_index:         int                 = 0
    description:        str                 = ""
    intended_action:    str                 = ""
    tool_name:          str                 = ""
    parameters:         dict[str, Any]      = field(default_factory=dict)
    dependencies:       list[str]           = field(default_factory=list)  # step_ids

    # Verification specification
    verify_condition:   str | None          = None
    verify_tool:        str | None          = None
    verify_params:      dict[str, Any]      = field(default_factory=dict)

    # Runtime execution state
    status:             StepStatus          = StepStatus.PENDING
    result:             StepResult | None   = None
    observation:        str | None          = None
    verification_state: VerificationStatus  = VerificationStatus.NOT_RUN
    max_retries:        int                 = 2
    metadata:           dict[str, Any]      = field(default_factory=dict)

    def __init__(
        self,
        step_id: str | None = None,
        step_index: int = 0,
        description: str = "",
        intended_action: str = "",
        tool_name: str = "",
        parameters: dict[str, Any] | None = None,
        dependencies: list[str] | None = None,
        depends_on: list[str] | None = None,
        verify_condition: str | None = None,
        verify_tool: str | None = None,
        verify_params: dict[str, Any] | None = None,
        status: StepStatus | str = StepStatus.PENDING,
        result: StepResult | None = None,
        observation: str | None = None,
        verification_state: VerificationStatus | str = VerificationStatus.NOT_RUN,
        max_retries: int = 2,
        metadata: dict[str, Any] | None = None,
    ):
        self.step_id = step_id or str(uuid.uuid4())[:8]
        self.step_index = step_index
        self.description = description
        self.intended_action = intended_action or description
        self.tool_name = tool_name
        self.parameters = parameters if parameters is not None else {}
        self.dependencies = dependencies if dependencies is not None else (depends_on or [])
        self.verify_condition = verify_condition
        self.verify_tool = verify_tool
        self.verify_params = verify_params if verify_params is not None else {}
        self.status = StepStatus(status) if isinstance(status, str) else status
        self.result = result
        self.observation = observation
        self.verification_state = (
            VerificationStatus(verification_state)
            if isinstance(verification_state, str)
            else verification_state
        )
        self.max_retries = max_retries
        self.metadata = metadata if metadata is not None else {}

    @property
    def depends_on(self) -> list[str]:
        return self.dependencies

    @depends_on.setter
    def depends_on(self, value: list[str]) -> None:
        self.dependencies = value

    def is_complete(self) -> bool:
        return self.status in (StepStatus.SUCCESS, StepStatus.SKIPPED)

    def has_failed(self) -> bool:
        return self.status == StepStatus.FAILED

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id":            self.step_id,
            "step_index":         self.step_index,
            "description":        self.description,
            "intended_action":    self.intended_action,
            "tool_name":          self.tool_name,
            "parameters":         self.parameters,
            "dependencies":       self.dependencies,
            "verify_condition":   self.verify_condition,
            "verify_tool":        self.verify_tool,
            "verify_params":      self.verify_params,
            "status":             self.status.value if isinstance(self.status, StepStatus) else str(self.status),
            "result":             self.result.to_dict() if self.result else None,
            "observation":        self.observation,
            "verification_state": self.verification_state.value if isinstance(self.verification_state, VerificationStatus) else str(self.verification_state),
            "max_retries":        self.max_retries,
            "metadata":           self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskStep:
        raw_res = data.get("result")
        res = StepResult.from_dict(raw_res) if raw_res else None
        return cls(
            step_id            = data.get("step_id"),
            step_index         = int(data.get("step_index", 0)),
            description        = data.get("description", ""),
            intended_action    = data.get("intended_action", ""),
            tool_name          = data.get("tool_name", ""),
            parameters         = data.get("parameters", {}),
            dependencies       = data.get("dependencies", data.get("depends_on", [])),
            verify_condition   = data.get("verify_condition"),
            verify_tool        = data.get("verify_tool"),
            verify_params      = data.get("verify_params", {}),
            status             = StepStatus(data.get("status", StepStatus.PENDING.value)),
            result             = res,
            observation        = data.get("observation"),
            verification_state = VerificationStatus(data.get("verification_state", VerificationStatus.NOT_RUN.value)),
            max_retries        = int(data.get("max_retries", 2)),
            metadata           = data.get("metadata", {}),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> TaskStep:
        return cls.from_dict(json.loads(json_str))


# ---------------------------------------------------------------------------
# Plan Model
# ---------------------------------------------------------------------------

@dataclass
class Plan:
    """
    Structured ordered execution plan for a Task.
    """
    plan_id:            str                 = field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_id:            str                 = ""
    steps:              list[TaskStep]      = field(default_factory=list)
    current_step_index: int                 = 0
    status:             PlanStatus          = PlanStatus.DRAFT
    created_at:         float               = field(default_factory=time.time)
    updated_at:         float               = field(default_factory=time.time)
    metadata:           dict[str, Any]      = field(default_factory=dict)

    @property
    def current_step(self) -> TaskStep | None:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    @property
    def completed_steps(self) -> list[TaskStep]:
        return [s for s in self.steps if s.is_complete()]

    @property
    def failed_steps(self) -> list[TaskStep]:
        return [s for s in self.steps if s.has_failed()]

    @property
    def pending_steps(self) -> list[TaskStep]:
        return [s for s in self.steps if s.status == StepStatus.PENDING]

    @property
    def is_complete(self) -> bool:
        return len(self.steps) > 0 and len(self.completed_steps) == len(self.steps)

    def add_step(self, step: TaskStep) -> None:
        step.step_index = len(self.steps)
        self.steps.append(step)
        self.updated_at = time.time()

    def advance(self) -> bool:
        """Advance to next step. Returns True if a next step exists."""
        self.current_step_index += 1
        self.updated_at = time.time()
        return self.current_step_index < len(self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id":            self.plan_id,
            "task_id":            self.task_id,
            "steps":              [s.to_dict() for s in self.steps],
            "current_step_index": self.current_step_index,
            "status":             self.status.value,
            "created_at":         self.created_at,
            "updated_at":         self.updated_at,
            "metadata":           self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Plan:
        raw_steps = data.get("steps", [])
        steps = [TaskStep.from_dict(s) for s in raw_steps]
        return cls(
            plan_id            = data.get("plan_id", str(uuid.uuid4())[:8]),
            task_id            = data.get("task_id", ""),
            steps              = steps,
            current_step_index = int(data.get("current_step_index", 0)),
            status             = PlanStatus(data.get("status", PlanStatus.DRAFT.value)),
            created_at         = float(data.get("created_at", time.time())),
            updated_at         = float(data.get("updated_at", time.time())),
            metadata           = data.get("metadata", {}),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> Plan:
        return cls.from_dict(json.loads(json_str))


# ---------------------------------------------------------------------------
# Task / AgentTask Model
# ---------------------------------------------------------------------------

class AgentTask:
    """
    Represents an explicit task entity in the SentinelOS agent runtime.
    
    Holds:
    - Identity, objective, constraints, criteria, scope
    - Lifecycle state and transition history
    - Execution plan and active step tracking
    - Observations, tool results, errors, verification records
    """

    def __init__(
        self,
        objective: str = "",
        goal: str = "",
        task_id: str | None = None,
        context: dict[str, Any] | None = None,
        status: TaskStatus | str = TaskStatus.CREATED,
        mode: str = "chat",
        constraints: list[str] | None = None,
        success_criteria: list[str] | None = None,
        scope: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        plan: Plan | None = None,
        steps: list[TaskStep] | None = None,
        created_at: float | None = None,
        updated_at: float | None = None,
        started_at: float | None = None,
        completed_at: float | None = None,
        conclusion: str | None = None,
        report: dict | None = None,
        authorized_targets: list[str] | None = None,
        authorization_level: str = "local",
        current_step_index: int = 0,
    ):
        self.task_id = task_id or str(uuid.uuid4())
        self._objective = objective or goal or ""
        self.context = context if context is not None else {}
        self.mode = mode
        self.constraints = constraints if constraints is not None else []
        self.success_criteria = success_criteria if success_criteria is not None else []
        self.scope = scope if scope is not None else {}
        self.metadata = metadata if metadata is not None else {}

        # Timing
        now = time.time()
        self.created_at = created_at if created_at is not None else now
        self.updated_at = updated_at if updated_at is not None else now
        self.started_at = started_at
        self.completed_at = completed_at

        # Lifecycle status (internal attribute)
        if isinstance(status, str):
            status = TaskStatus(status)
        self._status: TaskStatus = status

        # Plan and step tracking
        if plan is not None:
            self._plan: Plan | None = plan
            self._plan.task_id = self.task_id
        elif steps is not None:
            self._plan = Plan(task_id=self.task_id, steps=steps, current_step_index=current_step_index)
        else:
            self._plan = None

        # State accumulations
        self.observations: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.recovery_attempts: int = 0
        self.replan_count: int = 0

        # Outcome
        self.conclusion = conclusion
        self.report = report

        # Authorization
        self.authorized_targets = authorized_targets if authorized_targets is not None else []
        self.authorization_level = authorization_level

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def objective(self) -> str:
        return self._objective

    @objective.setter
    def objective(self, val: str) -> None:
        self._objective = val
        self.updated_at = time.time()

    @property
    def goal(self) -> str:
        return self._objective

    @goal.setter
    def goal(self, val: str) -> None:
        self._objective = val
        self.updated_at = time.time()

    @property
    def status(self) -> TaskStatus:
        return self._status

    @status.setter
    def status(self, target: TaskStatus | str) -> None:
        if isinstance(target, str):
            target = TaskStatus(target)
        self.transition_to(target)

    @property
    def plan(self) -> Plan | None:
        return self._plan

    @plan.setter
    def plan(self, p: Plan | None) -> None:
        self.attach_plan(p)

    @property
    def steps(self) -> list[TaskStep]:
        if self._plan is not None:
            return self._plan.steps
        return []

    @steps.setter
    def steps(self, step_list: list[TaskStep]) -> None:
        if self._plan is None:
            self._plan = Plan(task_id=self.task_id, steps=step_list)
        else:
            self._plan.steps = step_list
        self.updated_at = time.time()

    @property
    def current_step_index(self) -> int:
        if self._plan is not None:
            return self._plan.current_step_index
        return 0

    @current_step_index.setter
    def current_step_index(self, index: int) -> None:
        if self._plan is not None:
            self._plan.current_step_index = index
            self.updated_at = time.time()

    @property
    def current_step(self) -> TaskStep | None:
        if self._plan is not None:
            return self._plan.current_step
        return None

    @property
    def completed_steps(self) -> list[TaskStep]:
        if self._plan is not None:
            return self._plan.completed_steps
        return []

    @property
    def failed_steps(self) -> list[TaskStep]:
        if self._plan is not None:
            return self._plan.failed_steps
        return []

    @property
    def pending_steps(self) -> list[TaskStep]:
        if self._plan is not None:
            return self._plan.pending_steps
        return []

    @property
    def elapsed_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.completed_at or time.time()
        return end - self.started_at

    # ------------------------------------------------------------------
    # Lifecycle Management
    # ------------------------------------------------------------------

    def transition_to(self, target_status: TaskStatus | str, reason: str | None = None) -> None:
        """
        Transition task to a new lifecycle state with strict validation.
        """
        if isinstance(target_status, str):
            target_status = TaskStatus(target_status)

        if self._status == target_status:
            return

        validate_lifecycle_transition(
            current=self._status,
            target=target_status,
            task_id=self.task_id,
            reason=reason or "",
        )

        old_status = self._status
        self._status = target_status
        self.updated_at = time.time()

        logger.info(
            f"Agent Task [{self.task_id[:8]}] lifecycle: {old_status.value} -> {target_status.value}"
            + (f" ({reason})" if reason else "")
        )

    def mark_started(self) -> None:
        self.started_at = time.time()
        # If in CREATED, transition to EXECUTING (or if in READY, to EXECUTING)
        if self._status in (TaskStatus.CREATED, TaskStatus.READY):
            self.transition_to(TaskStatus.EXECUTING, reason="Task execution started")
        else:
            self.updated_at = time.time()

    def mark_completed(self, conclusion: str = "") -> None:
        self.completed_at = time.time()
        self.conclusion = conclusion
        self.transition_to(TaskStatus.COMPLETED, reason=conclusion)

    def mark_failed(self, reason: str = "") -> None:
        self.completed_at = time.time()
        self.conclusion = reason
        self.transition_to(TaskStatus.FAILED, reason=reason)

    def mark_blocked(self, reason: str = "") -> None:
        self.conclusion = reason
        self.transition_to(TaskStatus.BLOCKED, reason=reason)

    def cancel(self, reason: str = "") -> None:
        self.completed_at = time.time()
        self.conclusion = reason or "Cancelled by user"
        self.transition_to(TaskStatus.CANCELLED, reason=self.conclusion)

    # ------------------------------------------------------------------
    # State Updates
    # ------------------------------------------------------------------

    def attach_plan(self, plan: Plan | None) -> None:
        self._plan = plan
        if plan is not None:
            plan.task_id = self.task_id
            logger.info(
                f"Agent Task [{self.task_id[:8]}] plan attached: [{plan.plan_id}] with {len(plan.steps)} steps"
            )
            # If in PLANNING, transition to READY
            if self._status == TaskStatus.PLANNING:
                self.transition_to(TaskStatus.READY, reason="Plan attached")
        self.updated_at = time.time()

    def advance(self) -> bool:
        """Advance to next step in plan. Returns True if next step exists."""
        self.updated_at = time.time()
        if self._plan is not None:
            return self._plan.advance()
        return False

    def add_observation(self, step_id: str, observation: str, data: Any = None) -> None:
        entry = {
            "step_id":     step_id,
            "observation": observation,
            "data":        data,
            "timestamp":   time.time(),
        }
        self.observations.append(entry)
        self.updated_at = time.time()
        logger.info(f"Agent Task [{self.task_id[:8]}] observation recorded: {observation[:80]}")

    def add_error(self, step_id: str, error: str, failure_class: FailureClass | None = None) -> None:
        entry = {
            "step_id":       step_id,
            "error":         error,
            "failure_class": failure_class.value if failure_class else None,
            "timestamp":     time.time(),
        }
        self.errors.append(entry)
        self.updated_at = time.time()
        logger.warning(f"Agent Task [{self.task_id[:8]}] error recorded: {error[:80]}")

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id":             self.task_id,
            "objective":           self.objective,
            "goal":                self.goal,
            "status":              self.status.value,
            "mode":                self.mode,
            "constraints":         self.constraints,
            "success_criteria":    self.success_criteria,
            "scope":               self.scope,
            "metadata":            self.metadata,
            "created_at":          self.created_at,
            "updated_at":          self.updated_at,
            "started_at":          self.started_at,
            "completed_at":        self.completed_at,
            "plan":                self._plan.to_dict() if self._plan else None,
            "steps":               [s.to_dict() for s in self.steps],
            "current_step_index":  self.current_step_index,
            "observations":        self.observations,
            "errors":              self.errors,
            "recovery_attempts":   self.recovery_attempts,
            "replan_count":        self.replan_count,
            "elapsed_seconds":     round(self.elapsed_seconds, 2),
            "conclusion":          self.conclusion,
            "report":              self.report,
            "authorization_level": self.authorization_level,
            "authorized_targets":  self.authorized_targets,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentTask:
        raw_plan = data.get("plan")
        plan_obj = Plan.from_dict(raw_plan) if raw_plan else None

        raw_steps = data.get("steps")
        step_objs = [TaskStep.from_dict(s) for s in raw_steps] if raw_steps and not plan_obj else None

        task = cls(
            objective           = data.get("objective", data.get("goal", "")),
            task_id             = data.get("task_id"),
            context             = data.get("context", {}),
            status              = TaskStatus(data.get("status", TaskStatus.CREATED.value)),
            mode                = data.get("mode", "chat"),
            constraints         = data.get("constraints", []),
            success_criteria    = data.get("success_criteria", []),
            scope               = data.get("scope", {}),
            metadata            = data.get("metadata", {}),
            plan                = plan_obj,
            steps               = step_objs,
            created_at          = data.get("created_at"),
            updated_at          = data.get("updated_at"),
            started_at          = data.get("started_at"),
            completed_at        = data.get("completed_at"),
            conclusion          = data.get("conclusion"),
            report              = data.get("report"),
            authorized_targets  = data.get("authorized_targets", []),
            authorization_level = data.get("authorization_level", "local"),
            current_step_index  = int(data.get("current_step_index", 0)),
        )
        task.observations = data.get("observations", [])
        task.errors = data.get("errors", [])
        task.recovery_attempts = int(data.get("recovery_attempts", 0))
        task.replan_count = int(data.get("replan_count", 0))
        return task

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> AgentTask:
        return cls.from_dict(json.loads(json_str))

    def summary(self) -> str:
        """Compact summary string for logging and CLI status."""
        total = len(self.steps)
        done  = len(self.completed_steps)
        fails = len(self.failed_steps)
        status_str = self.status.value.upper()
        running_tag = " [RUNNING]" if self.status in (
            TaskStatus.EXECUTING,
            TaskStatus.PLANNING,
            TaskStatus.VERIFYING,
            TaskStatus.RECOVERING,
        ) else ""
        return (
            f"[{self.task_id[:8]}] {status_str}{running_tag} "
            f"steps={done}/{total} errors={fails} "
            f"elapsed={self.elapsed_seconds:.1f}s"
        )


# Task is an exact alias for AgentTask
Task = AgentTask


# ---------------------------------------------------------------------------
# Agent State (session-level container)
# ---------------------------------------------------------------------------

@dataclass
class AgentState:
    """
    Session-level agent runtime state.
    
    Contains the currently active task, execution history, and runtime controls.
    """
    session_id:         str                 = field(default_factory=lambda: str(uuid.uuid4()))
    active_task:        AgentTask | None    = None
    task_history:       list[AgentTask]     = field(default_factory=list)
    execution_metadata: dict[str, Any]      = field(default_factory=dict)

    # Execution controls
    stop_requested:     bool                = False
    max_steps:          int                 = 30
    max_retries:        int                 = 2
    max_replans:        int                 = 3

    # ------------------------------------------------------------------
    # Properties accessing active task runtime state
    # ------------------------------------------------------------------

    @property
    def objective(self) -> str | None:
        return self.active_task.objective if self.active_task else None

    @property
    def lifecycle_state(self) -> TaskStatus | None:
        return self.active_task.status if self.active_task else None

    @property
    def current_step(self) -> TaskStep | None:
        return self.active_task.current_step if self.active_task else None

    @property
    def completed_steps(self) -> list[TaskStep]:
        return self.active_task.completed_steps if self.active_task else []

    @property
    def pending_steps(self) -> list[TaskStep]:
        return self.active_task.pending_steps if self.active_task else []

    @property
    def observations(self) -> list[dict[str, Any]]:
        return self.active_task.observations if self.active_task else []

    @property
    def tool_results(self) -> list[StepResult]:
        if not self.active_task or not self.active_task.steps:
            return []
        return [s.result for s in self.active_task.steps if s.result is not None]

    @property
    def errors(self) -> list[dict[str, Any]]:
        return self.active_task.errors if self.active_task else []

    @property
    def verification_results(self) -> list[dict[str, Any]]:
        if not self.active_task or not self.active_task.steps:
            return []
        records = []
        for s in self.active_task.steps:
            if s.result and s.result.verification_status != VerificationStatus.NOT_RUN:
                records.append({
                    "step_id": s.step_id,
                    "status": s.result.verification_status.value,
                    "detail": s.result.verification_detail,
                })
        return records

    @property
    def recovery_attempts(self) -> int:
        return self.active_task.recovery_attempts if self.active_task else 0

    @property
    def timestamps(self) -> dict[str, float | None]:
        if not self.active_task:
            return {}
        return {
            "created_at":   self.active_task.created_at,
            "updated_at":   self.active_task.updated_at,
            "started_at":   self.active_task.started_at,
            "completed_at": self.active_task.completed_at,
        }

    @property
    def is_running(self) -> bool:
        return (
            self.active_task is not None
            and self.active_task.status in (
                TaskStatus.PLANNING,
                TaskStatus.READY,
                TaskStatus.EXECUTING,
                TaskStatus.WAITING,
                TaskStatus.VERIFYING,
                TaskStatus.RECOVERING,
            )
        )

    # ------------------------------------------------------------------
    # State Operations
    # ------------------------------------------------------------------

    def set_task(self, task: AgentTask) -> None:
        self.active_task = task
        self.stop_requested = False

    def complete_task(self) -> None:
        if self.active_task:
            self.task_history.append(self.active_task)
            self.active_task = None

    def request_stop(self) -> None:
        self.stop_requested = True
        if self.active_task and self.active_task.status not in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        ):
            self.active_task.cancel(reason="Stop requested by user or host")

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id":         self.session_id,
            "is_running":         self.is_running,
            "stop_requested":     self.stop_requested,
            "max_steps":          self.max_steps,
            "max_retries":        self.max_retries,
            "max_replans":        self.max_replans,
            "execution_metadata": self.execution_metadata,
            "active_task":        self.active_task.to_dict() if self.active_task else None,
            "task_history":       [t.to_dict() for t in self.task_history],
            "task_history_count": len(self.task_history),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentState:
        active_raw = data.get("active_task")
        active = AgentTask.from_dict(active_raw) if active_raw else None
        history_raw = data.get("task_history", [])
        history = [AgentTask.from_dict(t) for t in history_raw]
        state = cls(
            session_id         = data.get("session_id", str(uuid.uuid4())),
            active_task        = active,
            task_history       = history,
            execution_metadata = data.get("execution_metadata", {}),
            stop_requested     = bool(data.get("stop_requested", False)),
            max_steps          = int(data.get("max_steps", 30)),
            max_retries        = int(data.get("max_retries", 2)),
            max_replans        = int(data.get("max_replans", 3)),
        )
        return state

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> AgentState:
        return cls.from_dict(json.loads(json_str))
