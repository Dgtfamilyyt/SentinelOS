from pathlib import Path
from tools.base import Tool


class CurrentDirectoryTool(Tool):

    name = "current_directory"

    description = "Returns the current working directory."

    def execute(self):
        return str(Path.cwd())