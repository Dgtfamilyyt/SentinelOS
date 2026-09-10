from tools.base import Tool
from tools.policy import PermissionClass
from tools.security import resolve_workspace_path


class ListFilesTool(Tool):

    name = "list_files"

    description = (
        "Lists files inside a Sentinel "
        "workspace directory."
    )

    category = "filesystem"

    permission = PermissionClass.READ_ONLY

    parameters = {
        "path": {
            "type": "string",
            "required": False,
            "default": ".",
        }
    }

    def execute(self, path="."):

        target = resolve_workspace_path(path)

        if not target.exists():
            raise FileNotFoundError(
                f"Directory not found: {path}"
            )

        if not target.is_dir():
            raise NotADirectoryError(
                f"Not a directory: {path}"
            )

        return sorted(
            item.name
            for item in target.iterdir()
        )
