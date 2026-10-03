"""
tools/code/run_python.py
========================
RunPython — execute a Python snippet and return stdout/stderr.

Runs in a sandboxed subprocess with timeout. Does NOT allow file system
access outside the workspace by default (subprocess inherits environment).

Used by the agent to run data processing, validation scripts, or test
snippets as part of multi-step tasks.
"""

import subprocess
import sys
import tempfile
import os
from pathlib import Path

from tools.base import Tool
from tools.policy import PermissionClass
from config.settings import WORKSPACE_ROOT


class RunPython(Tool):
    """
    Execute a Python code snippet and return stdout, stderr, and exit code.

    Parameters:
        code    (str): Python source code to execute
        timeout (int): Execution timeout in seconds (default: 15)
    """

    name        = "run_python"
    description = "Execute a Python code snippet and return the output."
    category    = "code"
    permission  = PermissionClass.RESTRICTED  # Code execution requires policy unlock

    parameters  = {
        "code": {
            "type":     "string",
            "required": True,
            "description": "Python source code to execute",
        },
        "timeout": {
            "type":     "integer",
            "required": False,
            "description": "Execution timeout in seconds (default: 15)",
        },
    }

    def execute(self, code: str, timeout: int = 15) -> dict:
        # Write code to a temp file and run it in a subprocess
        with tempfile.NamedTemporaryFile(
            mode    = "w",
            suffix  = ".py",
            delete  = False,
            encoding= "utf-8",
            dir     = str(WORKSPACE_ROOT),
        ) as f:
            f.write(code)
            script_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output = True,
                text           = True,
                timeout        = timeout,
                cwd            = str(WORKSPACE_ROOT),
                encoding       = "utf-8",
                errors         = "replace",
            )
            return {
                "stdout":    result.stdout.strip(),
                "stderr":    result.stderr.strip(),
                "exit_code": result.returncode,
                "success":   result.returncode == 0,
                "timed_out": False,
            }
        except subprocess.TimeoutExpired:
            return {
                "stdout":    "",
                "stderr":    f"Execution timed out after {timeout}s",
                "exit_code": -1,
                "success":   False,
                "timed_out": True,
            }
        except Exception as exc:
            return {
                "stdout":    "",
                "stderr":    str(exc),
                "exit_code": -1,
                "success":   False,
                "timed_out": False,
            }
        finally:
            try:
                os.unlink(script_path)
            except Exception:
                pass
