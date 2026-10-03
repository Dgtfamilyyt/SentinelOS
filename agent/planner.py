"""
agent/planner.py
================
AgentPlanner — multi-step goal decomposition for the agent loop.

Produces an ordered list of TaskStep objects from a user goal.
Each step maps to one tool call with explicit verification conditions.

This is separate from the existing ai/planner.py (which handles single-step
routing for chat/tool dispatch). This planner produces full action sequences
for the agent loop.

The planner uses:
1. Fast-path: single-tool goals that don't need decomposition
2. Full decomposition: LLM-driven multi-step plan generation
3. Replan: given a failure context, produce revised steps
"""

from __future__ import annotations

import json
import re
from typing import Any

from agent.state import TaskStep, AgentTask
from core.logger import logger


# ---------------------------------------------------------------------------
# Planner prompts
# ---------------------------------------------------------------------------

AGENT_PLANNER_PROMPT = """\
You are the action-planning engine for Sentinel, an agentic AI system.

Your job: decompose the user's goal into an ordered sequence of concrete tool calls.

Available tools:
{tools}

RULES:
1. Return ONLY a valid JSON array of step objects. No markdown, no explanation.
2. Each step uses exactly one tool from the available list.
3. Include a verify_condition for any step that changes state (creates file, starts service, etc.)
4. Steps execute in order. Use depends_on to note dependencies between steps.
5. Do NOT invent tools. Only use tools from the available list.
6. If the goal cannot be completed with available tools, return an empty array [].
7. Keep descriptions short and action-focused.

Step schema:
{{
  "description": "short action description",
  "tool_name": "registered_tool_name",
  "parameters": {{}},
  "verify_condition": "what to check after (or null)",
  "verify_tool": "tool_to_run_for_verification (or null)",
  "verify_params": {{}},
  "max_retries": 2
}}

Task mode: {mode}
Authorized targets: {authorized_targets}
"""

AGENT_REPLAN_PROMPT = """\
You are the replanning engine for Sentinel.

The agent attempted to execute a plan but encountered a failure.

Original goal: {goal}
Failure context: {failure_context}

Completed steps so far:
{completed_steps}

Available tools:
{tools}

Produce a revised action sequence (JSON array) to achieve the original goal,
working around the failure. If the goal is now unachievable, return [].
"""


class AgentPlanner:
    """
    Multi-step planner for the agent loop.

    Produces TaskStep sequences from goals. Supports initial planning and
    failure-triggered replanning.
    """

    def __init__(self, tool_manager, ai_client, model_router):
        self._tools  = tool_manager
        self._client = ai_client
        self._router = model_router

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def plan_steps(self, task: AgentTask) -> list[TaskStep]:
        """
        Decompose a task goal into an ordered list of TaskStep objects.

        Returns [] if the goal is a pure reasoning task (no tool steps needed).
        """
        # Fast-path: simple single-tool goals
        fast = self._fast_path(task.goal, task.mode)
        if fast is not None:
            return fast

        # Check if any tools are even available
        tool_names = self._tools.names()
        if not tool_names:
            logger.warning("AgentPlanner: no tools registered, cannot produce action steps")
            return []

        raw = self._call_llm(
            AGENT_PLANNER_PROMPT.format(
                tools            = self._tool_catalog(),
                mode             = task.mode,
                authorized_targets = ", ".join(task.authorized_targets) or "local only",
            ),
            task.goal,
        )

        steps = self._parse_steps(raw)
        _index_steps(steps)
        logger.info(f"AgentPlanner: produced {len(steps)} steps for task {task.task_id[:8]}")
        return steps

    def replan_steps(self, task: AgentTask, failure_context: str) -> list[TaskStep]:
        """
        Produce a revised step sequence after a failure.
        """
        completed = [s.to_dict() for s in task.completed_steps]

        raw = self._call_llm(
            AGENT_REPLAN_PROMPT.format(
                goal             = task.goal,
                failure_context  = failure_context,
                completed_steps  = json.dumps(completed, indent=2),
                tools            = self._tool_catalog(),
            ),
            "",  # No separate user message for replan
        )

        steps = self._parse_steps(raw)
        _index_steps(steps, start_index=len(task.completed_steps))
        logger.info(f"AgentPlanner: replanned {len(steps)} steps for task {task.task_id[:8]}")
        return steps

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _tool_catalog(self) -> str:
        catalog = [t.info() for t in self._tools.all()]
        return json.dumps(catalog, indent=2)

    def _call_llm(self, system_prompt: str, user_message: str) -> str:
        model = self._router.choose("planning")
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        if user_message:
            messages.append({"role": "user", "content": user_message})
        try:
            return self._client.generate(model=model, messages=messages)
        except Exception as exc:
            logger.error(f"AgentPlanner: LLM call failed — {exc}")
            return "[]"

    @staticmethod
    def _parse_steps(raw: str) -> list[TaskStep]:
        """Parse LLM JSON output into TaskStep objects."""
        text = raw.strip()

        # Strip markdown fences
        if text.startswith("```"):
            lines = text.splitlines()
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # Extract JSON array
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            text = match.group(0)

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning(f"AgentPlanner: JSON parse error — {exc} | raw={text[:200]}")
            return []

        if not isinstance(data, list):
            return []

        steps = []
        for item in data:
            if not isinstance(item, dict):
                continue
            tool = item.get("tool_name", "")
            if not tool:
                continue
            step = TaskStep(
                description      = item.get("description", tool),
                tool_name        = tool,
                parameters       = item.get("parameters") or {},
                verify_condition = item.get("verify_condition"),
                verify_tool      = item.get("verify_tool"),
                verify_params    = item.get("verify_params") or {},
                max_retries      = int(item.get("max_retries", 2)),
            )
            steps.append(step)

        return steps

    def _fast_path(self, goal: str, mode: str) -> list[TaskStep] | None:
        """
        Detect simple goals that don't need LLM decomposition.
        Returns a step list if fast-path applies, else None.
        """
        text = goal.strip().lower()

        # Pure file operations
        if text in {"list files", "show files", "show workspace files"}:
            return [TaskStep(
                description = "List workspace files",
                tool_name   = "list_files",
                parameters  = {},
            )]

        if text in {"current directory", "show current directory"}:
            return [TaskStep(
                description = "Show current directory",
                tool_name   = "current_directory",
                parameters  = {},
            )]

        if text.startswith("read "):
            filename = goal.strip()[5:].strip()
            return [TaskStep(
                description      = f"Read file: {filename}",
                tool_name        = "read_file",
                parameters       = {"filename": filename},
                verify_condition = "file contents not empty",
            )]

        if text.startswith("create folder ") or text.startswith("mkdir "):
            folder = re.sub(r"^(create folder|mkdir)\s+", "", goal.strip(), flags=re.I)
            return [TaskStep(
                description      = f"Create folder: {folder}",
                tool_name        = "create_folder",
                parameters       = {"folder_name": folder},
                verify_condition = "folder exists",
            )]

        # Pure reasoning — no tool steps
        reasoning_only = any(re.search(r"\b" + kw + r"\b", text) for kw in [
            "explain", "what is", "how does", "describe", "tell me", "define",
            "summarize", "compare", "why", "when", "who",
        ])
        if reasoning_only:
            return []   # Empty list → loop skips to AI reasoning

        return None   # None → full LLM decomposition


def _index_steps(steps: list[TaskStep], start_index: int = 0) -> None:
    """Assign sequential step_index values in place."""
    for i, step in enumerate(steps):
        step.step_index = start_index + i
