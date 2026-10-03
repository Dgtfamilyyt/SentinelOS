"""
agent/reporter.py
=================
AgentReporter — generates the final structured report after an agent run.

Every agent task ends with a report that documents:
- Original goal
- Plan that was executed
- Each step: tool, parameters, result, verification
- Key observations
- Errors and recovery attempts
- Final conclusion and success/failure determination

This is the agent's "what I did and why" document.
"""

from __future__ import annotations

import json
import time
from typing import Any

from agent.state import AgentTask, TaskStatus, VerificationStatus
from core.logger import logger


class AgentReporter:
    """
    Generates structured reports from completed AgentTask objects.
    """

    def generate(self, task: AgentTask) -> dict:
        """
        Build the final report dict for a task.
        Populates task.report in place and returns it.
        """
        report = {
            "task_id":          task.task_id,
            "goal":             task.goal,
            "status":           task.status.value,
            "success":          task.status == TaskStatus.COMPLETED,
            "conclusion":       task.conclusion,
            "mode":             task.mode,
            "elapsed_seconds":  round(task.elapsed_seconds, 2),
            "authorization":    task.authorization_level,
            "steps":            self._format_steps(task),
            "observations":     task.observations,
            "errors":           task.errors,
            "recovery_attempts":task.recovery_attempts,
            "replan_count":     task.replan_count,
            "verified_outcomes":self._collect_verified(task),
            "summary":          self._generate_summary(task),
        }

        task.report = report
        logger.info(f"AgentReporter: report generated for task {task.task_id[:8]}")
        return report

    def format_text(self, task: AgentTask) -> str:
        """
        Generate a human-readable text version of the report.
        """
        report = task.report or self.generate(task)
        lines  = []

        status_icon = "✅" if report["success"] else "❌"
        lines.append(f"\n{'='*60}")
        lines.append(f"SENTINEL AGENT REPORT  {status_icon}")
        lines.append(f"{'='*60}")
        lines.append(f"Goal:     {report['goal']}")
        lines.append(f"Status:   {report['status'].upper()}")
        lines.append(f"Mode:     {report['mode']}")
        lines.append(f"Duration: {report['elapsed_seconds']}s")
        lines.append(f"Auth:     {report['authorization']}")
        lines.append("")

        if report["steps"]:
            lines.append("── EXECUTION STEPS ──────────────────────────────────")
            for step in report["steps"]:
                icon = "✓" if step["success"] else "✗"
                v = step.get("verification", "")
                v_tag = f" [verified: {v}]" if v and v != "not_run" else ""
                lines.append(
                    f"  [{step['index']}] {icon} {step['description']}"
                    f"\n       tool={step['tool']} | "
                    f"{'ok' if step['success'] else 'FAILED: ' + str(step.get('error', ''))}"
                    f"{v_tag}"
                )
            lines.append("")

        if report["observations"]:
            lines.append("── KEY OBSERVATIONS ──────────────────────────────────")
            for obs in report["observations"]:
                lines.append(f"  • [{obs['step_id']}] {obs['observation']}")
            lines.append("")

        if report["errors"]:
            lines.append("── ERRORS & RECOVERY ─────────────────────────────────")
            for err in report["errors"]:
                fc = err.get("failure_class") or "unknown"
                lines.append(f"  ✗ [{err['step_id']}] {err['error']} ({fc})")
            lines.append("")

        lines.append("── CONCLUSION ────────────────────────────────────────")
        lines.append(f"  {report['conclusion']}")
        lines.append(f"{'='*60}\n")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_steps(task: AgentTask) -> list[dict]:
        formatted = []
        for step in task.steps:
            result = step.result
            formatted.append({
                "index":        step.step_index,
                "step_id":      step.step_id,
                "description":  step.description,
                "tool":         step.tool_name,
                "parameters":   step.parameters,
                "status":       step.status.value,
                "success":      result.success if result else False,
                "output":       str(result.raw_output)[:500] if result else None,
                "error":        result.error if result else None,
                "retries":      result.retry_count if result else 0,
                "execution_ms": result.execution_time_ms if result else 0,
                "verification": result.verification_status.value if result else "not_run",
            })
        return formatted

    @staticmethod
    def _collect_verified(task: AgentTask) -> list[dict]:
        verified = []
        for step in task.steps:
            if (step.result and
                step.result.verification_status == VerificationStatus.PASSED):
                verified.append({
                    "step_id":     step.step_id,
                    "description": step.description,
                    "detail":      step.result.verification_detail,
                })
        return verified

    @staticmethod
    def _generate_summary(task: AgentTask) -> str:
        total  = len(task.steps)
        done   = sum(1 for s in task.steps if s.is_complete())
        failed = sum(1 for s in task.steps if s.has_failed())

        parts = [f"Executed {done}/{total} steps."]
        if failed:
            parts.append(f"{failed} step(s) failed.")
        if task.replan_count:
            parts.append(f"Replanned {task.replan_count} time(s).")
        if task.recovery_attempts:
            parts.append(f"{task.recovery_attempts} recovery attempt(s).")

        return " ".join(parts)
