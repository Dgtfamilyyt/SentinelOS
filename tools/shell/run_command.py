"""
tools/shell/run_command.py
==========================
RunCommand — execute a shell command and capture stdout/stderr.

This is the primary "computer control" tool. It gives the agent the ability
to run any command on the local machine.

Security model:
- Permission class: ELEVATED (requires explicit policy unlock)
- Workspace restriction: commands run in the configured workspace by default
- Timeout: enforced (default 30s, configurable)
- Output: captured and returned, not streamed
"""

import subprocess
import shlex
import platform
from pathlib import Path

from tools.base import Tool
from tools.policy import PermissionClass
from config.settings import WORKSPACE_ROOT


class RunCommand(Tool):
    """
    Execute a shell command and return stdout, stderr, and exit code.

    The command runs in the Sentinel workspace directory by default.
    Override with the ``cwd`` parameter.

    Parameters:
        command (str):   The command to run (passed to shell)
        cwd     (str):   Working directory (default: workspace root)
        timeout (int):   Seconds before killing the process (default: 30)
        shell   (bool):  Run via system shell (default: True on Windows)
    """

    name        = "run_command"
    description = "Execute a shell command and return stdout, stderr, and exit code."
    category    = "shell"
    permission  = PermissionClass.RESTRICTED   # Requires policy unlock

    parameters  = {
        "command": {
            "type":     "string",
            "required": True,
            "description": "The command to execute",
        },
        "cwd": {
            "type":     "string",
            "required": False,
            "description": "Working directory (default: Sentinel workspace)",
        },
        "timeout": {
            "type":     "integer",
            "required": False,
            "description": "Timeout in seconds (default: 30)",
        },
    }

    def execute(self, command: str, cwd: str = None, timeout: int = 30) -> dict:
        """
        Run the command. Returns:
            stdout:    captured standard output
            stderr:    captured standard error
            exit_code: process exit code
            timed_out: True if process was killed due to timeout
        """
        work_dir = Path(cwd) if cwd else WORKSPACE_ROOT
        work_dir.mkdir(parents=True, exist_ok=True)

        is_windows = platform.system() == "Windows"

        try:
            proc = subprocess.run(
                command,
                shell       = True,               # Always use shell for flexibility
                cwd         = str(work_dir),
                capture_output = True,
                text        = True,
                timeout     = timeout,
                encoding    = "utf-8",
                errors      = "replace",
            )

            return {
                "command":   command,
                "stdout":    proc.stdout.strip(),
                "stderr":    proc.stderr.strip(),
                "exit_code": proc.returncode,
                "success":   proc.returncode == 0,
                "timed_out": False,
                "cwd":       str(work_dir),
            }

        except subprocess.TimeoutExpired:
            return {
                "command":   command,
                "stdout":    "",
                "stderr":    f"Command timed out after {timeout} seconds",
                "exit_code": -1,
                "success":   False,
                "timed_out": True,
                "cwd":       str(work_dir),
            }

        except Exception as exc:
            return {
                "command":   command,
                "stdout":    "",
                "stderr":    str(exc),
                "exit_code": -1,
                "success":   False,
                "timed_out": False,
                "cwd":       str(work_dir),
            }
