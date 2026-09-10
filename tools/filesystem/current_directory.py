from tools.base import Tool
from tools.policy import PermissionClass
from tools.security import ensure_workspace
from config.settings import WORKSPACE_ROOT


class CurrentDirectoryTool(Tool):

    name = "current_directory"

    description = (
        "Returns the Sentinel workspace directory."
    )

    category = "filesystem"

    permission = PermissionClass.READ_ONLY

    parameters = {}

    def execute(self):
        ensure_workspace()

        return str(WORKSPACE_ROOT)
