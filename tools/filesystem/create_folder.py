from tools.base import Tool
from tools.security import resolve_workspace_path


class CreateFolderTool(Tool):

    name = "create_folder"

    description = (
        "Creates a directory inside "
        "the Sentinel workspace."
    )

    category = "filesystem"

    parameters = {
        "folder_name": {
            "type": "string",
            "required": True,
        }
    }

    def execute(self, folder_name):

        path = resolve_workspace_path(
            folder_name
        )

        path.mkdir(
            parents=True,
            exist_ok=True
        )

        return str(path)