from pathlib import Path
from tools.base import Tool


class CreateFolderTool(Tool):

    name = "create_folder"

    description = "Creates a folder."

    def execute(self, folder):

        Path(folder).mkdir(
            parents=True,
            exist_ok=True
        )

        return f"Folder '{folder}' created."