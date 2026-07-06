import os
from tools.base import Tool


class ListFilesTool(Tool):

    name = "list_files"

    category = "filesystem"

    description = "Lists all files and folders."

    parameters = []

    safe = True

    def execute(self):
        return os.listdir()