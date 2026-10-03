"""
agent/goal.py
=============
Goal Understanding and Task Ingestion layer for SentinelOS.

Transforms raw user requests into structured, validated Task specifications:
USER REQUEST -> GOAL UNDERSTANDING -> TASK SPECIFICATION -> AGENT TASK -> AGENT STATE

Model-independent, non-autonomous, does NOT execute tools or modify files.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.logger import logger
from agent.state import (
    AgentTask,
    Task,
    TaskStatus,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AuthorizationContext(str, Enum):
    """
    Explicit authorization context for an ingested task.
    
    Security rule: The LLM model is NOT an authorization authority.
    Authorization is determined by configuration, caller, or host policy.
    """
    UNSPECIFIED           = "unspecified"
    LOCAL                 = "local"
    EXPLICITLY_AUTHORIZED = "explicitly_authorized"
    AUTHORIZED_LAB        = "authorized_lab"
    RESTRICTED            = "restricted"
    UNKNOWN               = "unknown"

    @classmethod
    def _missing_(cls, value: object) -> Any:
        if isinstance(value, str):
            v = value.strip().lower()
            for member in cls:
                if member.value == v:
                    return member
        return cls.UNKNOWN


class TaskMode(str, Enum):
    """
    Operating modes for structured tasks.
    """
    GENERAL        = "general"
    DEVELOPMENT    = "development"
    ANALYSIS       = "analysis"
    RESEARCH       = "research"
    CYBER          = "cyber"
    DEFENSIVE      = "defensive"
    AUTHORIZED_LAB = "authorized_lab"

    @classmethod
    def normalize(cls, raw: str) -> str:
        text = (raw or "").strip().lower()
        mapping = {
            "chat": cls.GENERAL.value,
            "general": cls.GENERAL.value,
            "coding": cls.DEVELOPMENT.value,
            "development": cls.DEVELOPMENT.value,
            "dev": cls.DEVELOPMENT.value,
            "analysis": cls.ANALYSIS.value,
            "purple": cls.ANALYSIS.value,
            "research": cls.RESEARCH.value,
            "cyber": cls.CYBER.value,
            "security": cls.CYBER.value,
            "soc": cls.DEFENSIVE.value,
            "blue": cls.DEFENSIVE.value,
            "defensive": cls.DEFENSIVE.value,
            "red": cls.AUTHORIZED_LAB.value,
            "lab": cls.AUTHORIZED_LAB.value,
            "authorized_lab": cls.AUTHORIZED_LAB.value,
        }
        return mapping.get(text, cls.GENERAL.value)


# ---------------------------------------------------------------------------
# Structured Task Specification
# ---------------------------------------------------------------------------

@dataclass
class TaskSpecification:
    """
    Structured outcome of the Goal Understanding engine.
    
    Explicitly separates:
    - OBJECTIVE: The desired outcome / end-state
    - ACTION: The operational activity
    - SUCCESS CRITERIA: How completion can be verified
    - SCOPE: Explicitly bounded operational area
    - CONSTRAINTS: Express limitations
    - AMBIGUITY / MISSING INFORMATION: Missing parameters preventing safe execution
    """
    objective:             str
    action:                str                     = ""
    scope:                 dict[str, Any]          = field(default_factory=dict)
    constraints:           list[str]               = field(default_factory=list)
    success_criteria:      list[str]               = field(default_factory=list)
    mode:                  str                     = TaskMode.GENERAL.value
    authorization_context: str                     = AuthorizationContext.UNSPECIFIED.value
    metadata:              dict[str, Any]          = field(default_factory=dict)
    missing_information:   list[str]               = field(default_factory=list)
    is_ambiguous:          bool                    = False
    is_actionable:         bool                    = True
    confidence:            float                   = 1.0
    rationale_summary:     str                     = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective":             self.objective,
            "action":                self.action,
            "scope":                 self.scope,
            "constraints":           self.constraints,
            "success_criteria":      self.success_criteria,
            "mode":                  self.mode,
            "authorization_context": self.authorization_context,
            "metadata":              self.metadata,
            "missing_information":   self.missing_information,
            "is_ambiguous":          self.is_ambiguous,
            "is_actionable":         self.is_actionable,
            "confidence":            self.confidence,
            "rationale_summary":     self.rationale_summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskSpecification:
        return cls(
            objective             = str(data.get("objective", "")).strip(),
            action                = str(data.get("action", "")).strip(),
            scope                 = dict(data.get("scope", {})) if isinstance(data.get("scope"), dict) else {},
            constraints           = [str(c) for c in data.get("constraints", [])] if isinstance(data.get("constraints"), list) else [],
            success_criteria      = [str(s) for s in data.get("success_criteria", [])] if isinstance(data.get("success_criteria"), list) else [],
            mode                  = TaskMode.normalize(data.get("mode", TaskMode.GENERAL.value)),
            authorization_context = str(data.get("authorization_context", AuthorizationContext.UNSPECIFIED.value)),
            metadata              = dict(data.get("metadata", {})) if isinstance(data.get("metadata"), dict) else {},
            missing_information   = [str(m) for m in data.get("missing_information", [])] if isinstance(data.get("missing_information"), list) else [],
            is_ambiguous          = bool(data.get("is_ambiguous", False)),
            is_actionable         = bool(data.get("is_actionable", True)),
            confidence            = float(data.get("confidence", 1.0)),
            rationale_summary     = str(data.get("rationale_summary", "")),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> TaskSpecification:
        return cls.from_dict(json.loads(json_str))

    def to_task(self, task_id: str | None = None) -> Task:
        """
        Convert validated specification into a concrete SentinelOS Task.
        """
        is_blocked = (not self.is_actionable) and bool(self.missing_information)
        status = TaskStatus.BLOCKED if is_blocked else TaskStatus.CREATED
        conclusion = (
            f"Awaiting missing information: {', '.join(self.missing_information)}"
            if is_blocked
            else None
        )

        task_metadata = dict(self.metadata)
        task_metadata.update({
            "action":              self.action,
            "is_ambiguous":        self.is_ambiguous,
            "is_actionable":       self.is_actionable,
            "missing_information": self.missing_information,
            "confidence":          self.confidence,
            "rationale_summary":   self.rationale_summary,
        })

        task = Task(
            task_id             = task_id or str(uuid.uuid4()),
            objective           = self.objective,
            constraints         = list(self.constraints),
            success_criteria    = list(self.success_criteria),
            scope               = dict(self.scope),
            metadata            = task_metadata,
            mode                = self.mode,
            authorization_level = self.authorization_context,
            status              = status,
            conclusion          = conclusion,
        )
        return task


# ---------------------------------------------------------------------------
# Schema Validator
# ---------------------------------------------------------------------------

class TaskSpecificationValidator:
    """
    Validates structured task specifications against schema and security policies.
    """

    @classmethod
    def validate(
        cls,
        raw_data: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> TaskSpecification:
        if not isinstance(raw_data, dict):
            raise ValueError("Task specification must be a dictionary.")

        objective = str(raw_data.get("objective", "")).strip()
        if not objective:
            raise ValueError("Task specification missing required field: 'objective'.")

        action = str(raw_data.get("action", "")).strip()
        if not action:
            action = objective

        scope = raw_data.get("scope", {})
        if not isinstance(scope, dict):
            if isinstance(scope, str) and scope.strip():
                scope = {"type": "target", "target": scope.strip()}
            else:
                scope = {}

        constraints = raw_data.get("constraints", [])
        if not isinstance(constraints, list):
            constraints = [str(constraints)] if constraints else []
        constraints = [str(c).strip() for c in constraints if str(c).strip()]

        success_criteria = raw_data.get("success_criteria", [])
        if not isinstance(success_criteria, list):
            success_criteria = [str(success_criteria)] if success_criteria else []
        success_criteria = [str(sc).strip() for sc in success_criteria if str(sc).strip()]
        if not success_criteria:
            success_criteria = [f"Outcome verified for: {objective}"]

        mode = TaskMode.normalize(raw_data.get("mode", TaskMode.GENERAL.value))

        # Authorization validation (Security Rule 18)
        auth_raw = str(raw_data.get("authorization_context", AuthorizationContext.UNSPECIFIED.value)).lower().strip()
        ctx_targets = (context or {}).get("authorized_targets", [])
        ctx_auth_level = (context or {}).get("authorization_level")

        # Never permit self-authorization without explicit caller/system context
        if auth_raw in (AuthorizationContext.EXPLICITLY_AUTHORIZED.value, AuthorizationContext.AUTHORIZED_LAB.value):
            target_name = scope.get("target") or scope.get("path")
            has_explicit_context = bool(ctx_auth_level or (target_name and target_name in ctx_targets))
            if not has_explicit_context and scope.get("type") not in ("workspace", "local", "file", "directory"):
                auth_raw = AuthorizationContext.UNSPECIFIED.value
        elif auth_raw not in [m.value for m in AuthorizationContext]:
            auth_raw = AuthorizationContext.UNKNOWN.value

        missing_info = raw_data.get("missing_information", [])
        if not isinstance(missing_info, list):
            missing_info = [str(missing_info)] if missing_info else []
        missing_info = [str(m).strip() for m in missing_info if str(m).strip()]

        is_ambiguous = bool(raw_data.get("is_ambiguous", False)) or bool(missing_info)
        is_actionable = bool(raw_data.get("is_actionable", True)) and not bool(missing_info)

        try:
            confidence = float(raw_data.get("confidence", 1.0))
            confidence = max(0.0, min(1.0, confidence))
        except (ValueError, TypeError):
            confidence = 1.0

        rationale = str(raw_data.get("rationale_summary", "")).strip()

        return TaskSpecification(
            objective             = objective,
            action                = action,
            scope                 = scope,
            constraints           = constraints,
            success_criteria      = success_criteria,
            mode                  = mode,
            authorization_context = auth_raw,
            metadata              = raw_data.get("metadata", {}),
            missing_information   = missing_info,
            is_ambiguous          = is_ambiguous,
            is_actionable         = is_actionable,
            confidence            = confidence,
            rationale_summary     = rationale,
        )


# ---------------------------------------------------------------------------
# Goal Understanding Engine
# ---------------------------------------------------------------------------

class GoalUnderstandingEngine:
    """
    Transforms user-level requests into validated, structured Task representations.
    
    Combines:
    1. Deterministic fast path for common, unambiguous operations
    2. LLM structured-output path for complex reasoning
    3. Safe deterministic fallback parser for unparseable responses
    """

    def __init__(self, ai_client=None, model_router=None) -> None:
        self.client = ai_client
        self.router = model_router

    def understand(
        self,
        raw_request: str,
        context: dict[str, Any] | None = None,
    ) -> TaskSpecification:
        """
        Convert a raw user request into a structured TaskSpecification.
        """
        text = (raw_request or "").strip()
        if not text:
            return TaskSpecification(
                objective           = "No goal provided",
                is_ambiguous        = True,
                is_actionable       = False,
                missing_information = ["user_goal"],
                confidence          = 0.0,
            )

        # 1. Deterministic Fast Path
        fast_spec = self._match_fast_path(text, context)
        if fast_spec is not None:
            return TaskSpecificationValidator.validate(fast_spec.to_dict(), context)

        # 2. LLM Path (if client available)
        if self.client is not None:
            try:
                llm_spec = self._model_path(text, context)
                if llm_spec is not None:
                    return TaskSpecificationValidator.validate(llm_spec.to_dict(), context)
            except Exception as exc:
                logger.warning(f"GoalUnderstandingEngine: model path failed ({exc}); falling back to heuristic")

        # 3. Deterministic Heuristic Fallback Path
        fallback_spec = self._fallback_heuristic(text, context)
        return TaskSpecificationValidator.validate(fallback_spec.to_dict(), context)

    def ingest(
        self,
        raw_request: str,
        context: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> Task:
        """
        Directly ingest raw request into an Agent Kernel Task.
        """
        spec = self.understand(raw_request, context=context)
        task = spec.to_task(task_id=task_id)
        if context:
            task.context.update(context)

        logger.info(
            f"GoalUnderstandingEngine: ingested task [{task.task_id[:8]}] "
            f"objective='{task.objective[:80]}' mode='{task.mode}' actionable={spec.is_actionable}"
        )
        return task

    # ------------------------------------------------------------------
    # Fast Path Matching
    # ------------------------------------------------------------------

    def _match_fast_path(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> TaskSpecification | None:
        normalized = re.sub(r"[^\w\s/\.]", "", text.lower().strip()).rstrip('.').strip()

        # Workspace file inspection
        if normalized in {
            "list files",
            "show files",
            "list files in workspace",
            "list the files in the sentinelos workspace",
            "list the files in the workspace",
            "show workspace files",
            "inspect workspace",
            "inspect the workspace",
            "inspect the current sentinelos workspace",
            "inspect the current sentinelos workspace.",
        }:
            return TaskSpecification(
                objective             = "Inspect and list files in the SentinelOS workspace",
                action                = "Enumerate workspace directory contents",
                scope                 = {"type": "workspace", "path": "."},
                constraints           = ["read_only", "workspace_sandbox"],
                success_criteria      = [
                    "workspace directory enumerated",
                    "workspace files and directories collected",
                ],
                mode                  = TaskMode.GENERAL.value,
                authorization_context = AuthorizationContext.LOCAL.value,
                is_ambiguous          = False,
                is_actionable         = True,
                confidence            = 1.0,
                rationale_summary     = "Fast-path detection: workspace enumeration request",
            )

        # Current workspace directory
        if normalized in {
            "current directory",
            "current workspace",
            "show current directory",
            "where am i",
        }:
            return TaskSpecification(
                objective             = "Determine current SentinelOS workspace directory",
                action                = "Query active workspace root path",
                scope                 = {"type": "workspace", "path": "."},
                constraints           = ["read_only"],
                success_criteria      = ["workspace root path retrieved"],
                mode                  = TaskMode.GENERAL.value,
                authorization_context = AuthorizationContext.LOCAL.value,
                is_ambiguous          = False,
                is_actionable         = True,
                confidence            = 1.0,
            )

        # Read file
        read_match = re.match(r"^(?:read|show|view|cat)\s+(?:the\s+)?(?:file\s+)?([^\s]+)$", normalized)
        if read_match:
            filename = read_match.group(1).strip()
            return TaskSpecification(
                objective             = f"Read contents of file '{filename}'",
                action                = f"Read file '{filename}' from workspace",
                scope                 = {"type": "file", "path": filename},
                constraints           = ["read_only", "workspace_sandbox"],
                success_criteria      = [
                    f"file '{filename}' read successfully",
                    "content extracted without error",
                ],
                mode                  = TaskMode.GENERAL.value,
                authorization_context = AuthorizationContext.LOCAL.value,
                is_ambiguous          = False,
                is_actionable         = True,
                confidence            = 0.98,
            )

        # Create folder
        create_folder_match = re.match(
            r"^(?:create|make|mkdir)\s+(?:a\s+)?(?:project\s+)?folder\s+(?:called\s+|named\s+)?([^\s]+)$",
            normalized,
        )
        if create_folder_match:
            foldername = create_folder_match.group(1).strip()
            return TaskSpecification(
                objective             = f"Create project folder '{foldername}'",
                action                = f"Create new folder '{foldername}' in workspace",
                scope                 = {"type": "directory", "path": foldername},
                constraints           = ["workspace_sandbox"],
                success_criteria      = [
                    f"folder '{foldername}' created in workspace",
                    "folder existence confirmed",
                ],
                mode                  = TaskMode.DEVELOPMENT.value,
                authorization_context = AuthorizationContext.LOCAL.value,
                is_ambiguous          = False,
                is_actionable         = True,
                confidence            = 0.98,
            )

        # Test failure diagnosis (Prompt 5 example)
        if any(phrase in normalized for phrase in [
            "check why the sentinelos tests are failing",
            "check why tests are failing",
            "why are tests failing",
            "diagnose failing tests",
        ]):
            return TaskSpecification(
                objective             = "Identify the cause of failing SentinelOS tests",
                action                = "Execute test suite and analyze failure tracebacks",
                scope                 = {"type": "repository", "path": "tests"},
                constraints           = ["workspace_sandbox"],
                success_criteria      = [
                    "test execution telemetry captured",
                    "failing test root causes identified and reported",
                ],
                mode                  = TaskMode.DEVELOPMENT.value,
                authorization_context = AuthorizationContext.LOCAL.value,
                is_ambiguous          = False,
                is_actionable         = True,
                confidence            = 0.95,
                rationale_summary     = "Fast-path detection: test failure diagnosis",
            )

        # Ambiguous network scanning without target (Prompt 11/20 example C)
        if normalized in {
            "scan the server",
            "scan server",
            "scan the server.",
            "port scan the server",
            "scan a server",
        }:
            return TaskSpecification(
                objective             = "Perform network scan against server",
                action                = "Execute port enumeration",
                scope                 = {"type": "unknown"},
                constraints           = [],
                success_criteria      = ["specified server scanned"],
                mode                  = TaskMode.CYBER.value,
                authorization_context = AuthorizationContext.UNSPECIFIED.value,
                missing_information   = ["target_host_or_ip", "authorized_scope", "scan_parameters"],
                is_ambiguous          = True,
                is_actionable         = False,
                confidence            = 0.90,
                rationale_summary     = "Target server and authorized scope were not specified by the user.",
            )

        return None

    # ------------------------------------------------------------------
    # Model Path
    # ------------------------------------------------------------------

    def _model_path(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> TaskSpecification | None:
        from ai.prompts import GOAL_UNDERSTANDING_PROMPT

        model = "planner"
        if self.router is not None:
            model = self.router.choose("planning")

        messages = [
            {"role": "system", "content": GOAL_UNDERSTANDING_PROMPT},
            {"role": "user", "content": text},
        ]
        raw_output = self.client.generate(model=model, messages=messages)
        if not raw_output:
            return None

        # Clean JSON fences if model emitted markdown
        cleaned = raw_output.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        data = json.loads(cleaned)
        if not isinstance(data, dict):
            return None

        return TaskSpecification.from_dict(data)

    # ------------------------------------------------------------------
    # Deterministic Heuristic Fallback
    # ------------------------------------------------------------------

    def _fallback_heuristic(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> TaskSpecification:
        lowered = text.lower()

        # Determine mode
        mode = TaskMode.GENERAL.value
        if any(w in lowered for w in ["code", "debug", "test", "python", "bug", "refactor"]):
            mode = TaskMode.DEVELOPMENT.value
        elif any(w in lowered for w in ["soc", "log", "incident", "siem", "alert", "threat"]):
            mode = TaskMode.DEFENSIVE.value
        elif any(w in lowered for w in ["exploit", "red team", "pentest", "privilege", "reverse shell", "payload"]):
            mode = TaskMode.AUTHORIZED_LAB.value
        elif any(w in lowered for w in ["malware", "scan", "packet", "port", "network"]):
            mode = TaskMode.CYBER.value

        # Separate objective from user command
        objective = text
        action = text
        if lowered.startswith("check why "):
            objective = "Identify the cause of " + text[10:].strip()
            action = "Inspect and analyze " + text[10:].strip()
        elif lowered.startswith("create a "):
            objective = "Create " + text[9:].strip()
            action = "Create " + text[9:].strip()
        elif lowered.startswith("find "):
            objective = "Locate " + text[5:].strip()
            action = "Search for " + text[5:].strip()

        # Scope detection
        scope: dict[str, Any] = {"type": "local"}
        if "workspace" in lowered:
            scope = {"type": "workspace", "path": "."}

        # Constraints
        constraints: list[str] = []
        if any(w in lowered for w in ["check", "inspect", "list", "read", "view", "analyze"]):
            constraints.append("read_only")
        if "workspace" in lowered or scope.get("type") == "workspace":
            constraints.append("workspace_sandbox")

        # Success criteria
        success_criteria = [f"Desired outcome achieved for: {objective}"]

        # Ambiguity check
        missing_info: list[str] = []
        is_actionable = True
        is_ambiguous = False

        if any(lowered.startswith(prefix) for prefix in ["scan the server", "scan server", "hack", "attack"]):
            missing_info.append("target_host_or_resource")
            missing_info.append("authorized_scope")
            is_actionable = False
            is_ambiguous = True

        return TaskSpecification(
            objective             = objective,
            action                = action,
            scope                 = scope,
            constraints           = constraints,
            success_criteria      = success_criteria,
            mode                  = mode,
            authorization_context = AuthorizationContext.LOCAL.value if is_actionable else AuthorizationContext.UNSPECIFIED.value,
            missing_information   = missing_info,
            is_ambiguous          = is_ambiguous,
            is_actionable         = is_actionable,
            confidence            = 0.85,
            rationale_summary     = "Heuristic parsing fallback applied",
        )
