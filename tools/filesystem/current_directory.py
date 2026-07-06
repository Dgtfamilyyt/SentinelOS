import os
from tools.base import Tool


class CurrentDirectoryTool(Tool):

    name = "current_directory"

    category = "filesystem"

    description = "Returns the current working directory."

    parameters = []

    safe = True

    def execute(self):
        return os.getcwd()