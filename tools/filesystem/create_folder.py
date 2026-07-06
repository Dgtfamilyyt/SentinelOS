import os
from tools.base import Tool


class CreateFolderTool(Tool):

    name = "create_folder"

    category = "filesystem"

    description = "Creates a new folder."

    parameters = ["folder_name"]

    safe = True

    def execute(self, folder_name):

        os.makedirs(folder_name, exist_ok=True)

        return f"Folder '{folder_name}' created."