from tools.base import Tool
from tools.security import resolve_workspace_path


class ReadFileTool(Tool):

    name = "read_file"

    description = (
        "Reads a text file located inside "
        "the Sentinel workspace."
    )

    category = "filesystem"

    parameters = {
        "filename": {
            "type": "string",
            "required": True,
        }
    }

    def execute(self, filename):

        path = resolve_workspace_path(
            filename
        )

        if not path.exists():
            raise FileNotFoundError(
                f"File not found: {filename}"
            )

        if not path.is_file():
            raise IsADirectoryError(
                f"Not a file: {filename}"
            )

        max_size = 1_000_000

        if path.stat().st_size > max_size:
            raise ValueError(
                "File is too large to read "
                "through this tool."
            )

        return path.read_text(
            encoding="utf-8",
            errors="replace"
        )