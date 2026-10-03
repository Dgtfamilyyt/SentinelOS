"""
tools/shell/write_file.py
=========================
WriteFile — write content to a file inside the Sentinel workspace.

Used by the agent to create or overwrite files during multi-step tasks.
"""

from pathlib import Path

from tools.base import Tool
from tools.policy import PermissionClass
from tools.security import resolve_workspace_path


class WriteFile(Tool):
    """
    Write text content to a file within the Sentinel workspace.

    Parameters:
        filename (str):  Relative path within the workspace
        content  (str):  Text content to write
        append   (bool): Append instead of overwrite (default: False)
    """

    name        = "write_file"
    description = "Write text content to a file within the Sentinel workspace."
    category    = "filesystem"
    permission  = PermissionClass.STATE_CHANGE

    parameters  = {
        "filename": {
            "type":     "string",
            "required": True,
            "description": "Relative filename within workspace",
        },
        "content": {
            "type":     "string",
            "required": True,
            "description": "Text content to write",
        },
        "append": {
            "type":     "boolean",
            "required": False,
            "description": "Append instead of overwrite (default: false)",
        },
    }

    def execute(self, filename: str, content: str, append: bool = False) -> dict:
        path = resolve_workspace_path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)

        mode = "a" if append else "w"
        path.write_text(content, encoding="utf-8") if not append else \
            open(path, "a", encoding="utf-8").write(content)

        return {
            "filename": str(path),
            "bytes_written": len(content.encode("utf-8")),
            "mode": "append" if append else "overwrite",
            "exists": path.exists(),
        }
