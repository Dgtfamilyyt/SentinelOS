import os

from tools.base import Tool


class ListFiles(Tool):

    name = "list_files"

    description = "List files inside a directory."

    category = "filesystem"

    parameters = {
        "path": "string"
    }

    def execute(self, path="."):

        return os.listdir(path)

