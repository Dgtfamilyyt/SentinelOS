from tools.registry import TOOLS


class ToolManager:

    def execute(self, tool_name, *args):

        tool = TOOLS.get(tool_name)

        if tool is None:
            return f"Unknown tool: {tool_name}"

        return tool.execute(*args)

    def available_tools(self):
        return list(TOOLS.keys())