import os

from tools.base import Tool


class CurrentDirectory(Tool):

    name = "current_directory"

    description = "Returns the current working directory."

    category = "system"

    parameters = {}

    def execute(self):
        return os.getcwd()