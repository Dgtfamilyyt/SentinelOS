"""
agent/executive.py
==================
AgentExecutive — replaces the stub core/executive.py

The executive is the authoritative entry point for all agentic goal processing.
It owns the AgentState for a session and delegates to the AgentLoop for actual
execution. The CommandCenter calls the executive; the executive manages
lifecycle (create task → run loop → collect result).
"""

from __future__ import annotations

import time
from typing import Any, Generator

from agent.state import (
    AgentState,
    AgentTask,
    TaskStatus,
)
from core.logger import logger


class AgentExecutive:
    """
    Session-level controller for agentic task execution.

    The executive:
    1. Creates an AgentTask from a user goal
    2. Delegates to AgentLoop for execution
    3. Manages stop/interrupt requests
    4. Returns structured results to the caller

    It intentionally does NOT contain execution logic — that belongs in
    agent/loop.py.
    """

    def __init__(
        self,
        loop,               # AgentLoop — injected to avoid circular imports
        goal_engine = None, # GoalUnderstandingEngine — optional goal understanding
        max_steps:  int = 30,
        max_retries:int = 2,
        max_replans:int = 3,
    ):
        self._loop        = loop
        self._goal_engine = goal_engine
        self._state       = AgentState(
            max_steps   = max_steps,
            max_retries = max_retries,
            max_replans = max_replans,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state.is_running

    def stop(self) -> None:
        """Request graceful stop of the current task."""
        self._state.request_stop()
        logger.info("AgentExecutive: stop requested")

    def run(
        self,
        goal:     str,
        context:  dict[str, Any] | None = None,
        mode:     str = "chat",
    ) -> dict[str, Any]:
        """
        Synchronous entry point. Creates a task, runs the loop, returns result.

        Returns a dict with keys:
            task_id, status, conclusion, steps, elapsed_seconds, report
        """
        if self._state.is_running:
            return {
                "success":    False,
                "error":      "An agent task is already running. Stop it first.",
                "task_id":    self._state.active_task.task_id if self._state.active_task else None,
            }

        task = self._create_task(goal, context or {}, mode)
        self._state.set_task(task)
        logger.info(f"AgentExecutive: starting task {task.task_id[:8]} — {goal[:80]}")

        try:
            for event in self._loop.run(task, self._state):
                # Events are yielded by the loop for streaming consumers.
                # In sync mode we just drain them (caller uses run_stream for SSE).
                _log_event(event)

        except Exception as exc:
            logger.exception("AgentExecutive: unhandled loop error")
            task.mark_failed(f"Unhandled error: {exc}")

        finally:
            self._state.complete_task()

        logger.info(f"AgentExecutive: task finished — {task.summary()}")

        return self._build_result(task)

    def run_stream(
        self,
        goal:    str,
        context: dict[str, Any] | None = None,
        mode:    str = "chat",
    ) -> Generator[dict, None, None]:
        """
        Streaming entry point — yields loop events as they are produced.

        Each yielded event is a dict with a ``type`` key.
        Consumers (API, CLI) can forward these as SSE or print them.
        """
        if self._state.is_running:
            yield {
                "type":    "error",
                "message": "An agent task is already running.",
            }
            return

        task = self._create_task(goal, context or {}, mode)
        self._state.set_task(task)
        logger.info(f"AgentExecutive: streaming task {task.task_id[:8]} — {goal[:80]}")

        try:
            yield {"type": "task_start", "task_id": task.task_id, "goal": goal}

            for event in self._loop.run(task, self._state):
                yield event

        except Exception as exc:
            logger.exception("AgentExecutive: unhandled loop error (stream)")
            task.mark_failed(f"Unhandled error: {exc}")
            yield {"type": "error", "message": str(exc)}

        finally:
            self._state.complete_task()

        yield {
            "type":    "task_complete",
            "task_id": task.task_id,
            "result":  self._build_result(task),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_task(
        self,
        goal:    str,
        context: dict[str, Any],
        mode:    str,
    ) -> AgentTask:
        if self._goal_engine is not None:
            task = self._goal_engine.ingest(goal, context=context)
            if mode and mode not in ("chat", "general"):
                task.mode = mode
            if task.status == TaskStatus.CREATED:
                task.mark_started()
                task.status = TaskStatus.PLANNING
            return task

        task = AgentTask(
            goal    = goal.strip(),
            context = context,
            mode    = mode,
        )
        task.mark_started()
        task.status = TaskStatus.PLANNING   # Immediately move to planning
        return task

    @staticmethod
    def _build_result(task: AgentTask) -> dict[str, Any]:
        return {
            "task_id":         task.task_id,
            "goal":            task.goal,
            "status":          task.status.value,
            "success":         task.status == TaskStatus.COMPLETED,
            "conclusion":      task.conclusion,
            "steps_total":     len(task.steps),
            "steps_completed": len(task.completed_steps),
            "steps_failed":    len(task.failed_steps),
            "observations":    task.observations,
            "errors":          task.errors,
            "elapsed_seconds": round(task.elapsed_seconds, 2),
            "report":          task.report,
        }


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _log_event(event: dict) -> None:
    event_type = event.get("type", "?")
    if event_type == "step_start":
        logger.info(f"  → Step [{event.get('step_index', '?')}] {event.get('description', '')}")
    elif event_type == "step_result":
        ok = event.get("success", False)
        logger.info(f"  {'✓' if ok else '✗'} {event.get('tool', '?')} — {'ok' if ok else event.get('error', 'failed')}")
    elif event_type == "verify":
        v = event.get("verification_status", "?")
        logger.info(f"  ✔ verify: {v}")
    elif event_type == "replan":
        logger.info(f"  ↺ replanning (attempt {event.get('attempt', '?')})")
    elif event_type == "blocked":
        logger.warning(f"  ⛔ blocked: {event.get('reason', '')}")
