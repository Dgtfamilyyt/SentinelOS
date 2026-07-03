from pathlib import Path
from tools.base import Tool


class ReadFileTool(Tool):

    name = "read_file"

    description = "Reads a text file."

    def execute(self, filename):

        path = Path(filename)

        if not path.exists():
            return "File not found."

        if path.is_dir():
            return "That is a directory."

        return path.read_text(encoding="utf-8")