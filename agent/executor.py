"""
agent/executor.py
=================
StepExecutor — wraps the ToolManager to execute a single TaskStep.

Responsibilities:
- Translate a TaskStep into a ToolManager.execute() call
- Normalize the result into a StepResult
- Classify failures into FailureClass values
- Never assume success; failure classification drives recovery

The executor does NOT retry — that is the loop's responsibility.
"""

from __future__ import annotations

import re
from typing import Any

from agent.state import (
    FailureClass,
    StepResult,
    TaskStep,
    AgentTask,
)
from core.logger import logger


# Patterns that indicate transient (retry-safe) failures
_TRANSIENT_PATTERNS = [
    r"timeout",
    r"timed out",
    r"connection reset",
    r"temporary failure",
    r"try again",
    r"resource temporarily unavailable",
    r"EAGAIN",
]

# Patterns indicating environmental failures (setup needed, not a logic error)
_ENVIRONMENTAL_PATTERNS = [
    r"not found",
    r"no such file",
    r"command not found",
    r"permission denied",
    r"access denied",
    r"insufficient permissions",
    r"tool not found",
    r"module not found",
    r"cannot find",
    r"not installed",
]


class StepExecutor:
    """
    Executes a TaskStep by calling the appropriate tool.

    Injected with the ToolManager so it has access to all registered tools
    and their execution policy.
    """

    def __init__(self, tool_manager):
        self._tools = tool_manager

    def execute(self, step: TaskStep, task: AgentTask) -> StepResult:
        """
        Execute the tool specified in the step.

        Returns a StepResult — NEVER raises. All exceptions are captured and
        classified into a StepResult with success=False.
        """
        logger.info(
            f"StepExecutor: [{step.step_id}] executing tool '{step.tool_name}' "
            f"params={list(step.parameters.keys())}"
        )

        # Build the result scaffold
        result = StepResult(
            step_id    = step.step_id,
            tool_name  = step.tool_name,
            parameters = step.parameters,
        )

        # Check the tool exists before trying
        if step.tool_name not in self._tools.names():
            result.success      = False
            result.error        = f"Tool not found: '{step.tool_name}'"
            result.failure_class= FailureClass.ENVIRONMENTAL
            logger.warning(f"StepExecutor: {result.error}")
            return result

        try:
            raw = self._tools.execute(step.tool_name, step.parameters)

            if isinstance(raw, dict):
                if raw.get("success"):
                    result.success    = True
                    result.raw_output = raw.get("result")
                else:
                    result.success      = False
                    result.error        = str(raw.get("error", "Tool returned failure"))
                    result.raw_output   = raw.get("result")
                    result.failure_class= self._classify(result.error)
            else:
                # Non-dict return — treat as success
                result.success    = True
                result.raw_output = raw

        except PermissionError as exc:
            result.success       = False
            result.error         = f"Permission denied: {exc}"
            result.failure_class = FailureClass.ENVIRONMENTAL
            logger.warning(f"StepExecutor: permission error — {exc}")

        except Exception as exc:
            result.success       = False
            result.error         = str(exc)
            result.failure_class = self._classify(str(exc))
            logger.exception(f"StepExecutor: unexpected error in tool '{step.tool_name}'")

        if not result.success:
            logger.warning(
                f"StepExecutor: step {step.step_id} FAILED "
                f"[{result.failure_class}] {result.error}"
            )

        return result

    @staticmethod
    def _classify(error_text: str) -> FailureClass:
        """Classify an error string into a FailureClass."""
        text = error_text.lower()

        for pattern in _TRANSIENT_PATTERNS:
            if re.search(pattern, text, re.I):
                return FailureClass.TRANSIENT

        for pattern in _ENVIRONMENTAL_PATTERNS:
            if re.search(pattern, text, re.I):
                return FailureClass.ENVIRONMENTAL

        return FailureClass.LOGICAL
