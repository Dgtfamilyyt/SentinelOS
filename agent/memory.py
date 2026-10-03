"""
agent/memory.py
===============
AgentMemory — per-task structured observation store.

Separate from chat history and persistent KV memory.
Stores the actual evidence collected during an agent run:
  - Tool outputs
  - Observations (summarized findings)
  - Errors
  - Verified outcomes

Backed by SQLite (same database connection as the rest of Sentinel).
Falls back to in-memory dict if DB is unavailable.
"""

from __future__ import annotations

import json
import time
from typing import Any

from core.logger import logger


class AgentMemory:
    """
    Per-task observation store.

    Usage:
        memory = AgentMemory()
        memory.record(task_id, step_id, "Found open port 22", {"port": 22})
        obs = memory.get_observations(task_id)
        memory.clear_task(task_id)
    """

    def __init__(self):
        self._store: dict[str, list[dict]] = {}   # task_id → list of records
        self._db_available = self._init_db()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        task_id:     str,
        step_id:     str,
        observation: str,
        data:        Any       = None,
        record_type: str       = "observation",
    ) -> None:
        """Store one observation for a task step."""
        entry = {
            "task_id":     task_id,
            "step_id":     step_id,
            "type":        record_type,
            "observation": observation,
            "data":        data,
            "timestamp":   time.time(),
        }

        # In-memory
        self._store.setdefault(task_id, []).append(entry)

        # Persist to DB if available
        if self._db_available:
            self._db_insert(entry)

    def record_error(
        self,
        task_id:  str,
        step_id:  str,
        error:    str,
        data:     Any = None,
    ) -> None:
        self.record(task_id, step_id, error, data, record_type="error")

    def record_verified(
        self,
        task_id: str,
        step_id: str,
        detail:  str,
    ) -> None:
        self.record(task_id, step_id, detail, record_type="verified_outcome")

    def get_observations(
        self,
        task_id:     str,
        record_type: str | None = None,
    ) -> list[dict]:
        """Return all observations (or a specific type) for a task."""
        entries = self._store.get(task_id, [])
        if record_type:
            return [e for e in entries if e["type"] == record_type]
        return list(entries)

    def get_summary(self, task_id: str) -> str:
        """Return a compact text summary of all observations for a task."""
        entries = self._store.get(task_id, [])
        if not entries:
            return "(no observations recorded)"

        lines = []
        for e in entries:
            prefix = {"observation": "•", "error": "✗", "verified_outcome": "✓"}.get(e["type"], "·")
            lines.append(f"[{e['step_id']}] {prefix} {e['observation']}")
        return "\n".join(lines)

    def clear_task(self, task_id: str) -> None:
        """Remove all in-memory observations for a task."""
        self._store.pop(task_id, None)

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def _init_db(self) -> bool:
        try:
            from database.connection import get_connection
            conn = get_connection()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_observations (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id     TEXT NOT NULL,
                    step_id     TEXT NOT NULL,
                    type        TEXT NOT NULL,
                    observation TEXT NOT NULL,
                    data        TEXT,
                    timestamp   REAL NOT NULL
                )
            """)
            conn.commit()
            conn.close()
            return True
        except Exception as exc:
            logger.warning(f"AgentMemory: DB init failed ({exc}), using in-memory only")
            return False

    def _db_insert(self, entry: dict) -> None:
        try:
            from database.connection import get_connection
            conn = get_connection()
            conn.execute(
                """
                INSERT INTO agent_observations
                    (task_id, step_id, type, observation, data, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry["task_id"],
                    entry["step_id"],
                    entry["type"],
                    entry["observation"],
                    json.dumps(entry["data"], default=str) if entry["data"] is not None else None,
                    entry["timestamp"],
                ),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning(f"AgentMemory: DB insert failed — {exc}")

    def get_task_history(
        self,
        task_id: str,
        limit:   int = 50,
    ) -> list[dict]:
        """Load observations from DB for a completed task."""
        if not self._db_available:
            return self.get_observations(task_id)
        try:
            from database.connection import get_connection
            conn   = get_connection()
            cursor = conn.execute(
                "SELECT step_id, type, observation, data, timestamp "
                "FROM agent_observations "
                "WHERE task_id = ? ORDER BY timestamp ASC LIMIT ?",
                (task_id, limit),
            )
            rows   = cursor.fetchall()
            conn.close()
            return [
                {
                    "step_id":     r[0],
                    "type":        r[1],
                    "observation": r[2],
                    "data":        json.loads(r[3]) if r[3] else None,
                    "timestamp":   r[4],
                }
                for r in rows
            ]
        except Exception as exc:
            logger.warning(f"AgentMemory: DB read failed — {exc}")
            return self.get_observations(task_id)
