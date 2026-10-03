"""
agent/recovery.py
=================
FailureRecovery — classifies failures and proposes recovery actions.

Recovery actions:
    retry      — step should be retried (loop handles backoff)
    skip       — step is non-critical, skip and continue
    replan     — current approach is invalid; ask planner for new steps
    continue   — inline fix applied; move on
    blocked    — failure requires human input or authorization

The recovery engine does NOT endlessly retry. Each action is bounded by
the AgentState configuration. The loop enforces the bounds.
"""

from __future__ import annotations

from agent.state import (
    FailureClass,
    StepResult,
    TaskStep,
    AgentTask,
    AgentState,
)
from core.logger import logger


class FailureRecovery:
    """
    Analyzes a failed step and proposes the best recovery action.

    Decision logic:
    1. If transient and under retry limit → loop will retry (we skip this step's result analysis)
    2. If environmental → attempt inline fix or surface as blocked
    3. If logical → replan
    4. If hard blocker → blocked
    5. If max retries exhausted → replan or blocked
    """

    # Errors that are unrecoverable without human intervention
    HARD_BLOCKER_PATTERNS = [
        "authorization",
        "not authorized",
        "requires human",
        "missing credentials",
        "api key",
        "authentication failed",
        "out of scope",
        "access denied",
    ]

    # Errors where skipping is safer than replanning
    SKIP_PATTERNS = [
        "optional",
        "not critical",
        "already exists",
        "already done",
        "nothing to do",
    ]

    def handle(
        self,
        step:   TaskStep,
        result: StepResult,
        task:   AgentTask,
        state:  AgentState,
    ) -> dict:
        """
        Determine recovery action for a failed step.

        Returns a dict with:
            action:  "retry" | "skip" | "replan" | "continue" | "blocked"
            detail:  human-readable explanation
            context: (optional) additional context for replanning
        """
        error_lower = (result.error or "").lower()
        fc          = result.failure_class

        logger.info(
            f"Recovery: step={step.step_id} class={fc} error='{result.error}'"
        )

        # ── Hard blocker check ────────────────────────────────────────
        if fc == FailureClass.HARD_BLOCKER or any(
            p in error_lower for p in self.HARD_BLOCKER_PATTERNS
        ):
            return {
                "action": "blocked",
                "detail": (
                    f"Hard blocker: {result.error}. "
                    "Human authorization or missing configuration required."
                ),
            }

        # ── Transient: retry budget not yet exhausted ─────────────────
        # (The loop handles retrying; by the time we reach here retries are done)
        if fc == FailureClass.TRANSIENT and result.retry_count < step.max_retries:
            return {
                "action": "retry",
                "detail": f"Transient failure, retrying ({result.retry_count + 1}/{step.max_retries}).",
            }

        # ── Skip-safe patterns ────────────────────────────────────────
        if any(p in error_lower for p in self.SKIP_PATTERNS):
            return {
                "action": "skip",
                "detail": f"Step is non-critical and can be skipped: {result.error}",
            }

        # ── Environmental: check if we can suggest an inline fix ──────
        if fc == FailureClass.ENVIRONMENTAL:
            inline_fix = self._suggest_env_fix(result.error, task)
            if inline_fix:
                return {
                    "action":  "continue",
                    "detail":  inline_fix,
                    "context": inline_fix,
                }
            # Environmental that we can't fix inline → replan
            return {
                "action":  "replan",
                "detail":  f"Environmental failure: {result.error}. Will replan around this constraint.",
                "context": (
                    f"The tool '{step.tool_name}' failed with environmental error: '{result.error}'. "
                    f"Replan without using this tool or suggest prerequisite steps."
                ),
            }

        # ── Logical: the approach is wrong → replan ───────────────────
        if fc == FailureClass.LOGICAL:
            return {
                "action":  "replan",
                "detail":  f"Logical failure: {result.error}. Replanning with corrected approach.",
                "context": (
                    f"Step '{step.description}' using tool '{step.tool_name}' with "
                    f"params {step.parameters} failed: '{result.error}'. "
                    f"The approach is incorrect. Replan with a different strategy."
                ),
            }

        # ── Default fallback: replan ──────────────────────────────────
        return {
            "action":  "replan",
            "detail":  f"Unknown failure: {result.error}. Replanning.",
            "context": f"Step failed unexpectedly: {result.error}",
        }

    @staticmethod
    def _suggest_env_fix(error: str, task: AgentTask) -> str | None:
        """
        Suggest an inline workaround for common environmental errors.
        Returns a human-readable suggestion or None if no fix is known.
        """
        lower = error.lower()

        if "not found" in lower and "tool" in lower:
            return "The required tool is not installed. Install it or use an alternative."

        if "permission denied" in lower or "access denied" in lower:
            return (
                "Permission denied. The agent may need elevated permissions. "
                "Consider running with appropriate privileges."
            )

        if "no such file or directory" in lower:
            return "Required file or directory does not exist. Create it first or adjust the path."

        return None
