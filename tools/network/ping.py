"""
tools/network/ping.py
=====================
PingTool — ICMP ping to test host reachability.
"""

import subprocess
import platform

from tools.base import Tool
from tools.policy import PermissionClass


class PingTool(Tool):
    """
    Ping a host and return reachability result.

    Parameters:
        host  (str): Target hostname or IP
        count (int): Number of ICMP packets (default: 4)
    """

    name        = "ping"
    description = "Ping a host to test ICMP reachability."
    category    = "network"
    permission  = PermissionClass.READ_ONLY

    parameters  = {
        "host": {
            "type":     "string",
            "required": True,
            "description": "Target hostname or IP address",
        },
        "count": {
            "type":     "integer",
            "required": False,
            "description": "Number of ICMP packets to send (default: 4)",
        },
    }

    def execute(self, host: str, count: int = 4) -> dict:
        is_windows = platform.system() == "Windows"
        flag = "-n" if is_windows else "-c"

        try:
            result = subprocess.run(
                ["ping", flag, str(count), host],
                capture_output = True,
                text           = True,
                timeout        = 10,
                encoding       = "utf-8",
                errors         = "replace",
            )
            reachable = result.returncode == 0
            return {
                "host":      host,
                "reachable": reachable,
                "output":    result.stdout.strip(),
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"host": host, "reachable": False, "output": "Ping timed out", "exit_code": -1}
        except Exception as exc:
            return {"host": host, "reachable": False, "output": str(exc), "exit_code": -1}
