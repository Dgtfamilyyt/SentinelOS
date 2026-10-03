"""
agent/loop.py
=============
The core agent execution loop.

Implements the cycle:
    GOAL → PLAN → SELECT_TOOL → EXECUTE → OBSERVE → VERIFY → UPDATE_STATE
        → NEXT_ACTION | REPLAN | COMPLETE | BLOCKED

The loop is a synchronous generator — each iteration yields an event dict
that represents what the agent is doing right now. Consumers (executive,
API, CLI) can stream these events in real time.

Design principles:
- No action is assumed successful without evidence
- Verification is mandatory for state-changing steps  
- Failures are classified and handled before giving up
- Replanning is bounded (max_replans)
- Hard blockers surface to the user rather than silent failure
"""

from __future__ import annotations

import time
from typing import Any, Generator

from agent.state import (
    AgentState,
    AgentTask,
    TaskStatus,
    TaskStep,
    StepStatus,
    StepResult,
    FailureClass,
    VerificationStatus,
)
from core.logger import logger


class AgentLoop:
    """
    Core execution loop for a single AgentTask.

    Dependencies are injected:
        planner      — produces TaskStep sequences from a goal
        executor     — executes a single TaskStep via the tool manager
        verifier     — confirms actual post-execution state
        recovery     — classifies failures and proposes corrections
        memory       — records observations per task
    """

    def __init__(
        self,
        planner,
        executor,
        verifier,
        recovery,
        memory,
    ):
        self._planner  = planner
        self._executor = executor
        self._verifier = verifier
        self._recovery = recovery
        self._memory   = memory

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(
        self,
        task:  AgentTask,
        state: AgentState,
    ) -> Generator[dict, None, None]:
        """
        Execute the task. Yields event dicts throughout execution.

        Event types:
            planning          — planner is building the step sequence
            plan_ready        — step sequence produced
            step_start        — about to execute a step
            step_result       — step execution finished
            verify_start      — verification is running
            verify_result     — verification outcome
            observation       — significant finding recorded
            recovery_start    — failure recovery triggered
            recovery_result   — recovery outcome
            replan            — replanning triggered
            blocked           — hard blocker, needs human
            loop_complete     — all steps done, task complete
        """
        # ── Phase 1: Planning ──────────────────────────────────────────
        yield {"type": "planning", "goal": task.goal}
        task.status = TaskStatus.PLANNING

        try:
            steps = self._planner.plan_steps(task)
        except Exception as exc:
            task.mark_failed(f"Planning failed: {exc}")
            yield {"type": "error", "phase": "planning", "message": str(exc)}
            return

        if not steps:
            # Planner returned no steps — this is a simple AI response, not an action task
            task.mark_completed("No tool steps required — handled as reasoning task.")
            yield {"type": "loop_complete", "conclusion": task.conclusion}
            return

        task.steps = steps
        task.status = TaskStatus.RUNNING
        yield {
            "type":  "plan_ready",
            "steps": [s.to_dict() for s in steps],
            "count": len(steps),
        }

        # ── Phase 2: Execution cycle ───────────────────────────────────
        step_ceiling = state.max_steps
        executed     = 0

        while task.current_step is not None:

            # Safety: stop if requested
            if state.stop_requested:
                task.status = TaskStatus.CANCELLED
                yield {"type": "cancelled", "reason": "stop requested"}
                return

            # Safety: step ceiling
            if executed >= step_ceiling:
                task.mark_blocked("Step ceiling reached — stopping to prevent runaway execution.")
                yield {"type": "blocked", "reason": task.conclusion}
                return

            step = task.current_step
            executed += 1

            # ── Execute one step ──────────────────────────────────────
            yield {
                "type":        "step_start",
                "step_id":     step.step_id,
                "step_index":  step.step_index,
                "description": step.description,
                "tool":        step.tool_name,
                "parameters":  step.parameters,
            }

            step.status = StepStatus.RUNNING
            result      = self._execute_with_retry(step, task, state)
            step.result = result

            yield {
                "type":       "step_result",
                "step_id":    step.step_id,
                "step_index": step.step_index,
                "tool":       step.tool_name,
                "success":    result.success,
                "output":     result.raw_output,
                "error":      result.error,
                "retries":    result.retry_count,
            }

            if not result.success:
                step.status = StepStatus.FAILED
                task.add_error(step.step_id, result.error or "unknown", result.failure_class)

                # ── Recovery ─────────────────────────────────────────
                yield {
                    "type":          "recovery_start",
                    "step_id":       step.step_id,
                    "failure_class": result.failure_class.value if result.failure_class else "unknown",
                }
                task.status = TaskStatus.RECOVERING

                recovery_action = self._recovery.handle(step, result, task, state)

                yield {
                    "type":   "recovery_result",
                    "action": recovery_action.get("action"),
                    "detail": recovery_action.get("detail"),
                }

                action = recovery_action.get("action")

                if action == "skip":
                    step.status = StepStatus.SKIPPED
                    if not task.advance():
                        break

                elif action == "replan":
                    task.replan_count += 1
                    if task.replan_count > state.max_replans:
                        task.mark_blocked(
                            f"Replan limit ({state.max_replans}) reached. "
                            f"Last error: {result.error}"
                        )
                        yield {"type": "blocked", "reason": task.conclusion}
                        return

                    yield {"type": "replan", "attempt": task.replan_count}
                    task.status = TaskStatus.PLANNING

                    try:
                        new_steps = self._planner.replan_steps(task, recovery_action.get("context", ""))
                    except Exception as exc:
                        task.mark_failed(f"Replan failed: {exc}")
                        yield {"type": "error", "phase": "replan", "message": str(exc)}
                        return

                    if new_steps:
                        # Replace remaining pending steps with new plan
                        done_steps = [s for s in task.steps if s.is_complete()]
                        task.steps = done_steps + new_steps
                        task.current_step_index = len(done_steps)
                        task.status = TaskStatus.RUNNING
                        yield {
                            "type":  "plan_ready",
                            "steps": [s.to_dict() for s in new_steps],
                            "count": len(new_steps),
                            "replan": True,
                        }
                    else:
                        task.mark_completed("Replanned with no further actions required.")
                        yield {"type": "loop_complete", "conclusion": task.conclusion}
                        return

                elif action == "blocked":
                    task.mark_blocked(recovery_action.get("detail", "Hard blocker encountered."))
                    yield {"type": "blocked", "reason": task.conclusion}
                    return

                else:
                    # "continue" — recovery attempted an inline fix, move on
                    step.status = StepStatus.SKIPPED
                    task.status = TaskStatus.RUNNING
                    if not task.advance():
                        break

                continue   # Back to top of while loop

            # ── Step succeeded ────────────────────────────────────────
            step.status = StepStatus.SUCCESS

            # Record observation
            obs = _summarize_output(result.raw_output)
            task.add_observation(step.step_id, obs, result.raw_output)
            self._memory.record(
                task_id     = task.task_id,
                step_id     = step.step_id,
                observation = obs,
                data        = result.raw_output,
            )
            yield {"type": "observation", "step_id": step.step_id, "observation": obs}

            # ── Verification ──────────────────────────────────────────
            if step.verify_condition or step.verify_tool:
                task.status = TaskStatus.VERIFYING
                yield {
                    "type":      "verify_start",
                    "step_id":   step.step_id,
                    "condition": step.verify_condition,
                }

                v_status, v_detail = self._verifier.verify(step, result, task)
                result.verification_status = v_status
                result.verification_detail = v_detail

                yield {
                    "type":    "verify_result",
                    "step_id": step.step_id,
                    "status":  v_status.value,
                    "detail":  v_detail,
                }

                if v_status == VerificationStatus.FAILED:
                    # Treat verification failure as step failure → recovery
                    step.status = StepStatus.FAILED
                    synthetic = StepResult(
                        step_id      = step.step_id,
                        tool_name    = step.verify_tool or "verifier",
                        parameters   = {},
                        success      = False,
                        error        = f"Verification failed: {v_detail}",
                        failure_class= FailureClass.LOGICAL,
                    )
                    task.add_error(step.step_id, synthetic.error, FailureClass.LOGICAL)

                    recovery_action = self._recovery.handle(step, synthetic, task, state)
                    action = recovery_action.get("action")

                    if action == "replan" and task.replan_count < state.max_replans:
                        task.replan_count += 1
                        yield {"type": "replan", "attempt": task.replan_count, "trigger": "verify_fail"}
                        try:
                            new_steps = self._planner.replan_steps(
                                task,
                                f"Verification failed for step {step.step_id}: {v_detail}"
                            )
                        except Exception as exc:
                            task.mark_failed(f"Replan after verify fail: {exc}")
                            yield {"type": "error", "phase": "replan", "message": str(exc)}
                            return

                        if new_steps:
                            done_steps = [s for s in task.steps if s.is_complete()]
                            task.steps = done_steps + new_steps
                            task.current_step_index = len(done_steps)
                            task.status = TaskStatus.RUNNING
                            continue
                    else:
                        task.mark_blocked(f"Verification failed and cannot recover: {v_detail}")
                        yield {"type": "blocked", "reason": task.conclusion}
                        return

                task.status = TaskStatus.RUNNING

            # Advance to next step
            if not task.advance():
                break

        # ── Phase 3: Completion ───────────────────────────────────────
        if task.status not in (TaskStatus.BLOCKED, TaskStatus.CANCELLED, TaskStatus.FAILED):
            conclusion = _build_conclusion(task)
            task.mark_completed(conclusion)

        yield {
            "type":       "loop_complete",
            "task_id":    task.task_id,
            "status":     task.status.value,
            "conclusion": task.conclusion,
            "steps_done": len(task.completed_steps),
            "steps_failed": len(task.failed_steps),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _execute_with_retry(
        self,
        step:  TaskStep,
        task:  AgentTask,
        state: AgentState,
    ) -> StepResult:
        """Execute a step, retrying on transient failures up to max_retries."""
        retries    = 0
        max_r      = min(step.max_retries, state.max_retries)
        last_result: StepResult | None = None

        while retries <= max_r:
            if retries > 0:
                logger.info(f"  ↻ retry {retries}/{max_r} for step {step.step_id}")
                step.status = StepStatus.RETRYING
                time.sleep(min(2 ** retries, 10))  # Exponential backoff, cap at 10s

            start = time.time()
            result = self._executor.execute(step, task)
            result.execution_time_ms = int((time.time() - start) * 1000)
            result.retry_count       = retries
            last_result              = result

            if result.success:
                return result

            # Only retry transient failures
            if result.failure_class != FailureClass.TRANSIENT:
                return result

            retries += 1

        return last_result  # type: ignore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _summarize_output(output: Any) -> str:
    """Produce a short human-readable summary of tool output."""
    if output is None:
        return "(no output)"
    if isinstance(output, str):
        lines = output.strip().splitlines()
        if len(lines) <= 3:
            return output.strip()
        return "\n".join(lines[:3]) + f"\n… ({len(lines)} lines total)"
    if isinstance(output, dict):
        keys = list(output.keys())[:5]
        return f"dict with keys: {keys}"
    if isinstance(output, list):
        return f"list of {len(output)} items"
    return str(output)[:200]


def _build_conclusion(task: AgentTask) -> str:
    total  = len(task.steps)
    done   = len(task.completed_steps)
    failed = len(task.failed_steps)

    if failed == 0:
        return f"Task completed successfully. {done}/{total} steps executed."
    elif done > failed:
        return (
            f"Task completed with partial success. "
            f"{done}/{total} steps succeeded, {failed} failed."
        )
    else:
        return (
            f"Task completed but most steps failed. "
            f"{failed}/{total} steps failed. Review errors."
        )
