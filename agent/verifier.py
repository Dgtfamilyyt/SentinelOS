"""
agent/verifier.py
=================
StateVerifier — confirms that an executed step actually achieved its intent.

A completed action is NOT the same as a completed objective.

The verifier runs AFTER a successful tool execution to confirm the intended
state change occurred. It uses:
1. A verification tool (if specified in the step)
2. Heuristic checks on the raw output
3. A quick LLM-based semantic check on the step's verify_condition

Verification is optional per step. Steps that are read-only or purely
informational often don't need verification.
"""

from __future__ import annotations

import re
from typing import Any

from agent.state import (
    FailureClass,
    StepResult,
    StepStatus,
    TaskStep,
    AgentTask,
    VerificationStatus,
)
from core.logger import logger


class StateVerifier:
    """
    Verifies that a step's execution actually achieved the intended outcome.

    Injected with the tool_manager (for running verification tools) and
    ai_engine (for semantic verification when a natural-language condition
    is specified).
    """

    def __init__(self, tool_manager, ai_engine=None):
        self._tools = tool_manager
        self._ai    = ai_engine

    def verify(
        self,
        step:   TaskStep,
        result: StepResult,
        task:   AgentTask,
    ) -> tuple[VerificationStatus, str]:
        """
        Verify a completed step.

        Returns (VerificationStatus, detail_string).
        """
        # If neither verification mechanism is specified, skip
        if not step.verify_condition and not step.verify_tool:
            return VerificationStatus.SKIPPED, "No verification condition specified."

        # ── Tool-based verification ────────────────────────────────────
        if step.verify_tool:
            logger.info(f"Verifier: running tool '{step.verify_tool}' for step {step.step_id}")
            try:
                v_raw = self._tools.execute(step.verify_tool, step.verify_params or {})
                if isinstance(v_raw, dict) and not v_raw.get("success"):
                    return (
                        VerificationStatus.FAILED,
                        f"Verification tool failed: {v_raw.get('error', 'unknown')}",
                    )
                v_output = v_raw.get("result") if isinstance(v_raw, dict) else v_raw

                if step.verify_condition:
                    passed = self._check_condition(step.verify_condition, v_output, result.raw_output)
                    if passed:
                        return VerificationStatus.PASSED, f"Condition satisfied: {step.verify_condition}"
                    else:
                        return (
                            VerificationStatus.FAILED,
                            f"Condition not met: '{step.verify_condition}' | output: {str(v_output)[:200]}",
                        )
                # Tool succeeded with no condition to check → assume pass
                return VerificationStatus.PASSED, "Verification tool ran successfully."

            except Exception as exc:
                logger.warning(f"Verifier: verification tool error — {exc}")
                return VerificationStatus.FAILED, f"Verification error: {exc}"

        # ── Heuristic / LLM verification (condition only) ─────────────
        if step.verify_condition:
            passed = self._check_condition(step.verify_condition, None, result.raw_output)
            if passed:
                return VerificationStatus.PASSED, f"Output satisfies: {step.verify_condition}"
            elif self._ai is not None:
                # Delegate to LLM for semantic check
                return self._ai_verify(step.verify_condition, result.raw_output, task)
            else:
                return (
                    VerificationStatus.FAILED,
                    f"Cannot confirm condition '{step.verify_condition}' from output.",
                )

        return VerificationStatus.SKIPPED, "Nothing to verify."

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_condition(condition: str, v_output: Any, raw_output: Any) -> bool:
        """
        Fast heuristic check for common conditions.

        Examples handled:
            "file exists"
            "service is running"
            "no error in output"
            "output contains <keyword>"
        """
        cond   = condition.lower().strip()
        output = str(v_output or raw_output or "").lower()

        # Positive keyword presence
        if "contains" in cond:
            keyword = re.sub(r".*contains\s+", "", cond).strip().strip("'\"")
            return keyword in output

        # Negative — no error
        if "no error" in cond or "without error" in cond:
            error_patterns = [r"\berror\b", r"\bfailed\b", r"\bexception\b", r"\btraceback\b"]
            return not any(re.search(p, output) for p in error_patterns)

        # Service / process running
        if "running" in cond or "is running" in cond:
            running_signals = ["running", "active", "started", "online", "up"]
            return any(s in output for s in running_signals)

        # File / directory exists
        if "exist" in cond:
            return "no such file" not in output and "not found" not in output and len(output) > 0

        # Output not empty
        if "not empty" in cond or "has output" in cond:
            return len(output.strip()) > 0

        # Success / OK in output
        if "success" in cond or "ok" in cond:
            return any(s in output for s in ["success", "ok", "done", "completed", "true"])

        return False

    def _ai_verify(
        self,
        condition: str,
        raw_output: Any,
        task: AgentTask,
    ) -> tuple[VerificationStatus, str]:
        """Use the AI engine to verify a condition semantically."""
        prompt = (
            f"You are verifying whether a condition is satisfied based on tool output.\n\n"
            f"Condition: {condition}\n\n"
            f"Tool output:\n{str(raw_output)[:1000]}\n\n"
            f"Reply with exactly one word: PASSED or FAILED, then one sentence explaining why."
        )
        try:
            answer = self._ai.ask(prompt, task="chat").strip()
            if answer.upper().startswith("PASSED"):
                return VerificationStatus.PASSED, answer
            return VerificationStatus.FAILED, answer
        except Exception as exc:
            return VerificationStatus.FAILED, f"AI verification error: {exc}"
