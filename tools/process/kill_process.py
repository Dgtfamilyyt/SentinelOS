"""
tools/process/kill_process.py
==============================
KillProcess — terminate a process by PID or name.
"""

import subprocess
import platform

from tools.base import Tool
from tools.policy import PermissionClass


class KillProcess(Tool):
    """
    Terminate a process by PID or name.

    Parameters:
        pid  (int): Process ID to kill (preferred)
        name (str): Process name to kill (kills ALL matching — use with care)
    """

    name        = "kill_process"
    description = "Terminate a process by PID or name."
    category    = "process"
    permission  = PermissionClass.RESTRICTED  # State-changing and potentially dangerous

    parameters  = {
        "pid": {
            "type":     "integer",
            "required": False,
            "description": "Process ID to terminate",
        },
        "name": {
            "type":     "string",
            "required": False,
            "description": "Process name to terminate (kills all matching)",
        },
    }

    def execute(self, pid: int = None, name: str = None) -> dict:
        if pid is None and name is None:
            return {"success": False, "error": "Must provide pid or name"}

        is_windows = platform.system() == "Windows"

        try:
            if pid is not None:
                if is_windows:
                    result = subprocess.run(
                        ["taskkill", "/PID", str(pid), "/F"],
                        capture_output=True, text=True,
                    )
                else:
                    result = subprocess.run(
                        ["kill", "-9", str(pid)],
                        capture_output=True, text=True,
                    )
                return {
                    "success":   result.returncode == 0,
                    "pid":       pid,
                    "output":    result.stdout.strip() or result.stderr.strip(),
                    "exit_code": result.returncode,
                }

            if name is not None:
                if is_windows:
                    result = subprocess.run(
                        ["taskkill", "/IM", name, "/F"],
                        capture_output=True, text=True,
                    )
                else:
                    result = subprocess.run(
                        ["pkill", "-f", name],
                        capture_output=True, text=True,
                    )
                return {
                    "success":   result.returncode == 0,
                    "name":      name,
                    "output":    result.stdout.strip() or result.stderr.strip(),
                    "exit_code": result.returncode,
                }

        except Exception as exc:
            return {"success": False, "error": str(exc)}
