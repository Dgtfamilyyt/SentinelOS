"""
agent/authorization.py
======================
AuthorizationModel — explicit, configurable scope and target policy.

Defines:
  - Authorized local operations (always allowed)
  - Authorized lab environments (explicitly configured)
  - Restricted operations (need elevated auth level)
  - Denied targets (outside any authorized scope)

The authorization model is the ONLY source of truth for whether an agent
action against a network target is permitted. It is separate from the LLM
system prompt — the LLM does not grant or deny authorization.

Configuration: config/authorized_targets.yaml (YAML file, hot-reloaded)
"""

from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.logger import logger


# ---------------------------------------------------------------------------
# Auth levels
# ---------------------------------------------------------------------------

AUTH_LOCAL    = "local"      # Local machine operations only
AUTH_LAB      = "lab"        # Authorized lab / CTF / test environment
AUTH_ELEVATED = "elevated"   # Explicitly elevated for a specific operation
AUTH_DENIED   = "denied"     # Explicitly outside scope


# ---------------------------------------------------------------------------
# Target entry
# ---------------------------------------------------------------------------

@dataclass
class AuthorizedTarget:
    """
    One authorized scope entry.

    label:      Human description (e.g. "Metasploitable VM", "HTB Lab")
    targets:    IP addresses, CIDR ranges, or hostnames
    auth_level: "lab" or "elevated"
    allowed_ops: Optional whitelist of operation categories
    notes:      Free-form notes for audit
    """
    label:       str
    targets:     list[str]
    auth_level:  str           = AUTH_LAB
    allowed_ops: list[str]     = field(default_factory=list)
    notes:       str           = ""


# ---------------------------------------------------------------------------
# Authorization model
# ---------------------------------------------------------------------------

class AuthorizationModel:
    """
    Determines whether an agent action against a target is authorized.

    Decision hierarchy:
    1. Local target (127.0.0.1, localhost, file operations) → always AUTH_LOCAL
    2. Target matches an authorized lab entry → AUTH_LAB
    3. Target explicitly denied → AUTH_DENIED
    4. Unknown target → AUTH_DENIED (fail-closed)
    """

    CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "authorized_targets.yaml"

    def __init__(self):
        self._authorized: list[AuthorizedTarget] = []
        self._denied:     list[str]              = []
        self._load_config()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(self, target: str) -> str:
        """
        Return the authorization level for a target.

        target: IP address, hostname, CIDR range, or None/empty for local ops
        """
        if not target or target.strip() == "":
            return AUTH_LOCAL

        target = target.strip().lower()

        # Localhost is always local
        if target in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return AUTH_LOCAL

        # Explicitly denied
        if self._is_denied(target):
            logger.warning(f"AuthorizationModel: DENIED — {target}")
            return AUTH_DENIED

        # Check authorized lab entries
        for entry in self._authorized:
            if self._matches_entry(target, entry):
                logger.info(f"AuthorizationModel: LAB authorized — {target} ({entry.label})")
                return entry.auth_level

        # Unknown → deny (fail-closed)
        logger.warning(f"AuthorizationModel: DENIED (unknown scope) — {target}")
        return AUTH_DENIED

    def is_authorized(self, target: str, required_level: str = AUTH_LAB) -> bool:
        """Check if target meets a minimum authorization level."""
        level = self.check(target)
        hierarchy = [AUTH_DENIED, AUTH_LOCAL, AUTH_LAB, AUTH_ELEVATED]
        try:
            return hierarchy.index(level) >= hierarchy.index(required_level)
        except ValueError:
            return False

    def authorize_task(self, task) -> None:
        """
        Populate a task's authorization_level and authorized_targets.
        Called by the executive before loop execution.
        """
        if not self._authorized:
            task.authorization_level = AUTH_LOCAL
            task.authorized_targets  = []
            return

        task.authorized_targets  = [
            t
            for entry in self._authorized
            for t in entry.targets
        ]
        task.authorization_level = AUTH_LAB

    def add_lab_target(
        self,
        label:   str,
        targets: list[str],
        notes:   str = "",
    ) -> None:
        """Runtime addition of an authorized target (not persisted)."""
        self._authorized.append(AuthorizedTarget(
            label      = label,
            targets    = targets,
            auth_level = AUTH_LAB,
            notes      = notes,
        ))
        logger.info(f"AuthorizationModel: added lab target '{label}' — {targets}")

    def get_authorized_targets(self) -> list[dict]:
        return [
            {
                "label":      e.label,
                "targets":    e.targets,
                "auth_level": e.auth_level,
                "notes":      e.notes,
            }
            for e in self._authorized
        ]

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        if not self.CONFIG_PATH.exists():
            logger.info("AuthorizationModel: no config file found, local-only mode")
            self._create_default_config()
            return

        try:
            import yaml  # type: ignore
            with open(self.CONFIG_PATH, "r") as f:
                data = yaml.safe_load(f) or {}
        except ImportError:
            data = self._parse_yaml_simple(self.CONFIG_PATH)
        except Exception as exc:
            logger.warning(f"AuthorizationModel: config load failed — {exc}")
            return

        for entry_data in data.get("authorized_targets", []):
            self._authorized.append(AuthorizedTarget(
                label       = entry_data.get("label", "unknown"),
                targets     = entry_data.get("targets", []),
                auth_level  = entry_data.get("auth_level", AUTH_LAB),
                allowed_ops = entry_data.get("allowed_ops", []),
                notes       = entry_data.get("notes", ""),
            ))

        self._denied = data.get("denied_targets", [])
        logger.info(
            f"AuthorizationModel: loaded {len(self._authorized)} authorized targets, "
            f"{len(self._denied)} denied"
        )

    def _create_default_config(self) -> None:
        """Create a starter config file if none exists."""
        self.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        template = """\
# Sentinel Authorization Model Configuration
# ============================================
# Add authorized lab environments below.
# The agent will ONLY execute network operations against listed targets.
# All other targets are DENIED (fail-closed).
#
# authorized_targets:
#   - label: "Metasploitable 2 VM"
#     targets:
#       - "192.168.56.101"
#     auth_level: "lab"
#     notes: "Local VirtualBox NAT network"
#
#   - label: "HackTheBox VPN"
#     targets:
#       - "10.10.0.0/16"
#     auth_level: "lab"
#     notes: "HTB VPN subnet"

authorized_targets: []

denied_targets: []
"""
        self.CONFIG_PATH.write_text(template)
        logger.info(f"AuthorizationModel: created default config at {self.CONFIG_PATH}")

    # ------------------------------------------------------------------
    # Internal matching
    # ------------------------------------------------------------------

    def _matches_entry(self, target: str, entry: AuthorizedTarget) -> bool:
        for authorized in entry.targets:
            if self._target_matches(target, authorized):
                return True
        return False

    @staticmethod
    def _target_matches(target: str, pattern: str) -> bool:
        """Match target against a pattern (exact, CIDR, wildcard, hostname glob)."""
        pattern = pattern.strip().lower()
        target  = target.strip().lower()

        if pattern == target:
            return True

        # CIDR range
        if "/" in pattern:
            try:
                network = ipaddress.ip_network(pattern, strict=False)
                addr    = ipaddress.ip_address(target)
                return addr in network
            except ValueError:
                pass

        # Wildcard hostname (e.g. *.lab.local)
        if "*" in pattern:
            regex = re.escape(pattern).replace(r"\*", ".*")
            return bool(re.fullmatch(regex, target))

        return False

    def _is_denied(self, target: str) -> bool:
        for denied in self._denied:
            if self._target_matches(target, denied):
                return True
        return False

    @staticmethod
    def _parse_yaml_simple(path: Path) -> dict:
        """Minimal YAML parser fallback (no PyYAML dependency)."""
        # For the default empty config this is sufficient
        return {"authorized_targets": [], "denied_targets": []}
