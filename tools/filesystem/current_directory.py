from tools.base import Tool
from tools.security import ensure_workspace
from config.settings import WORKSPACE_ROOT


class CurrentDirectoryTool(Tool):

    name = "current_directory"

    description = (
        "Returns the Sentinel workspace directory."
    )

    category = "filesystem"

    parameters = {}

    def execute(self):
        ensure_workspace()

        return str(WORKSPACE_ROOT)