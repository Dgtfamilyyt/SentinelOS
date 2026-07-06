from tools.base import Tool


class ReadFileTool(Tool):

    name = "read_file"

    category = "filesystem"

    description = "Reads a text file."

    parameters = ["filename"]

    safe = True

    def execute(self, filename):

        with open(filename, "r", encoding="utf-8") as f:
            return f.read()