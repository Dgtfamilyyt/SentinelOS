from pathlib import Path
from tools.base import Tool


class ListFilesTool(Tool):

    name = "list_files"

    description = "Lists files and folders in the current directory."

    def execute(self):

        return sorted(
            [item.name for item in Path.cwd().iterdir()]
        )