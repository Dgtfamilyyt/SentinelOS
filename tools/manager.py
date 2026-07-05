from tools.registry import TOOLS


class ToolManager:

    def execute(self, tool_name, *args, **kwargs):

        tool = TOOLS.get(tool_name)

        if tool is None:
            return f"Unknown tool: {tool_name}"

        return tool.execute(*args, **kwargs)

    def available_tools(self):
        return list(TOOLS.keys())

    def tool_descriptions(self):
        return [
            {
                "name": tool.name,
                "description": tool.description,
            }
            for tool in TOOLS.values()
        ]