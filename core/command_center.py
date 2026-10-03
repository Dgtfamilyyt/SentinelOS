"""
core/command_center.py
======================
CommandCenter — the session-level coordinator for all Sentinel processing.

Upgraded to support both:
  1. Single-step chat/tool dispatch (existing behavior, preserved)
  2. Full agentic loop (new) — multi-step goal execution via AgentExecutive

The agent mode is activated when:
  - The caller explicitly passes mode="agent"
  - The goal is complex enough that the AgentPlanner produces multi-step plans

Single-step mode (chat, single tool call) continues to use the fast
Dispatcher path, preserving all existing behavior and streaming.
"""

from __future__ import annotations

import threading
from contextlib import aclosing
from typing import Any, Generator

from ai.engine      import AIEngine
from ai.planner     import Planner
from ai.dispatcher  import Dispatcher
from tools.manager  import ToolManager
from tools.policy   import ExecutionPolicy
from core.logger    import logger
from agent.factory  import build_agent
from agent.goal     import GoalUnderstandingEngine, TaskSpecification
from agent.state    import Task


class CommandCenter:
    """
    Session-level coordinator.

    Provides:
        process(prompt)              → single-step result (existing)
        process_stream(...)          → streaming single-step (existing)
        run_agent(goal, ...)         → blocking agentic execution (new)
        run_agent_stream(goal, ...)  → streaming agentic execution (new)
        understand_goal(prompt, ...) → parse goal into structured TaskSpecification (MP2)
        ingest_task(prompt, ...)     → ingest goal into structured Agent Task (MP2)
    """

    def __init__(self, agent_policy: str = "agent"):
        # ── Existing components (unchanged) ───────────────────────────
        self.ai = AIEngine()

        self.tools = ToolManager(
            policy=ExecutionPolicy(
                ExecutionPolicy.AGENT_ALLOWED
                if agent_policy in ("agent", "lab")
                else ExecutionPolicy.DEFAULT_ALLOWED
            )
        )
        self.tools.discover()

        self.planner    = Planner(tool_manager=self.tools)
        self.dispatcher = Dispatcher(ai_engine=self.ai, tool_manager=self.tools)

        # ── Goal understanding engine (MP2) ───────────────────────────
        self.goal_engine = GoalUnderstandingEngine(
            ai_client    = self.ai.client,
            model_router = self.ai.router,
        )

        # ── Agent pipeline (new) ──────────────────────────────────────
        self._executive, self._auth, self._reporter = build_agent(
            tool_manager = self.tools,
            ai_client    = self.ai.client,
            model_router = self.ai.router,
            ai_engine    = self.ai,
        )
        self._agent_lock = threading.Lock()

    def understand_goal(
        self,
        prompt:  str,
        context: dict[str, Any] | None = None,
    ) -> TaskSpecification:
        """Parse raw goal into structured TaskSpecification."""
        return self.goal_engine.understand(prompt, context=context)

    def ingest_task(
        self,
        prompt:  str,
        context: dict[str, Any] | None = None,
    ) -> Task:
        """Ingest raw user request into a structured Agent Task."""
        return self.goal_engine.ingest(prompt, context=context)

    # ------------------------------------------------------------------
    # Existing single-step interface (preserved exactly)
    # ------------------------------------------------------------------

    def process(self, prompt: str) -> Any:
        """Single-step request → response (existing behavior)."""
        plan = self.planner.plan(prompt)
        return self.dispatcher.dispatch(prompt, plan)

    async def process_stream(
        self,
        prompt:   str,
        *,
        history:  list,
        memories: list,
        model:    str | None,
        runtime,
    ):
        """Streaming single-step (existing behavior)."""
        plan = None
        async with aclosing(self.planner.plan_stream(prompt, runtime, model=model)) as events:
            async for event in events:
                if event["type"] == "plan":
                    plan = event["plan"]
                else:
                    yield event
        async with aclosing(self.dispatcher.dispatch_stream(
            prompt, plan, history=history, memories=memories, model=model, runtime=runtime
        )) as events:
            async for event in events:
                yield event

    # ------------------------------------------------------------------
    # Agentic interface (new)
    # ------------------------------------------------------------------

    def run_agent(
        self,
        goal:    str,
        context: dict[str, Any] | None = None,
        mode:    str = "chat",
        auth_level: str | None = None,
    ) -> dict[str, Any]:
        """
        Run the agent loop synchronously. Returns the final result dict.
        Blocking — use run_agent_stream for progressive output.
        """
        with self._agent_lock:
            task_context = context or {}
            result = self._executive.run(goal, context=task_context, mode=mode)
            # Generate final report
            if self._executive.state.task_history:
                last_task = self._executive.state.task_history[-1]
                self._reporter.generate(last_task)
                result["report"] = last_task.report
            return result

    def run_agent_stream(
        self,
        goal:    str,
        context: dict[str, Any] | None = None,
        mode:    str = "chat",
    ) -> Generator[dict, None, None]:
        """
        Run the agent loop with streaming events.
        Yields event dicts as the agent executes.
        """
        if not self._agent_lock.acquire(blocking=False):
            yield {"type": "error", "message": "Agent is already running."}
            return
        try:
            yield from self._executive.run_stream(
                goal    = goal,
                context = context or {},
                mode    = mode,
            )
            # Generate and attach report to the last completed task
            if self._executive.state.task_history:
                last_task = self._executive.state.task_history[-1]
                report_text = self._reporter.format_text(last_task)
                yield {"type": "report", "text": report_text, "data": last_task.report}
        finally:
            self._agent_lock.release()

    def stop_agent(self) -> bool:
        """Request agent stop. Returns True if a task was running."""
        if self._executive.is_running:
            self._executive.stop()
            return True
        return False

    @property
    def agent_state(self) -> dict:
        """Return current agent state snapshot."""
        return self._executive.state.to_dict()

    @property
    def authorized_targets(self) -> list[dict]:
        """Return currently configured authorized targets."""
        return self._auth.get_authorized_targets()

    def add_lab_target(self, label: str, targets: list[str], notes: str = "") -> None:
        """Authorize a lab target at runtime."""
        self._auth.add_lab_target(label, targets, notes)
        logger.info(f"CommandCenter: added lab target '{label}'")
