class ToolRegistry:

    def __init__(self):
        self.tools = {}

    def register(self, tool):

        self.tools[tool.name] = tool

    def get(self, name):

        return self.tools.get(name)

    def all(self):

        return self.tools.values()

    def names(self):

        return list(self.tools.keys())