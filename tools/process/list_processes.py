"""
tools/process/list_processes.py
================================
ListProcesses — list running processes on the local system.
"""

import subprocess
import platform

from tools.base import Tool
from tools.policy import PermissionClass


class ListProcesses(Tool):
    """
    List running processes on the local system.

    Parameters:
        filter_name (str): Optional process name filter (case-insensitive substring)
    """

    name        = "list_processes"
    description = "List running processes on the local system."
    category    = "process"
    permission  = PermissionClass.READ_ONLY

    parameters  = {
        "filter_name": {
            "type":     "string",
            "required": False,
            "description": "Optional process name filter (case-insensitive substring match)",
        },
    }

    def execute(self, filter_name: str = None) -> dict:
        is_windows = platform.system() == "Windows"

        try:
            if is_windows:
                result = subprocess.run(
                    ["tasklist", "/FO", "CSV", "/NH"],
                    capture_output=True, text=True, timeout=10,
                )
                lines = [l.strip().strip('"').split('","') for l in result.stdout.strip().splitlines()]
                processes = [
                    {"name": p[0], "pid": p[1], "memory": p[4] if len(p) > 4 else ""}
                    for p in lines if p
                ]
            else:
                result = subprocess.run(
                    ["ps", "aux", "--no-headers"],
                    capture_output=True, text=True, timeout=10,
                )
                processes = []
                for line in result.stdout.strip().splitlines():
                    parts = line.split(None, 10)
                    if len(parts) >= 11:
                        processes.append({
                            "user": parts[0], "pid": parts[1],
                            "cpu": parts[2], "mem": parts[3],
                            "name": parts[10],
                        })

            if filter_name:
                fl = filter_name.lower()
                processes = [p for p in processes if fl in str(p.get("name", "")).lower()]

            return {
                "count":     len(processes),
                "processes": processes[:200],  # Cap at 200
                "filtered":  filter_name or None,
            }

        except Exception as exc:
            return {"error": str(exc), "processes": []}
