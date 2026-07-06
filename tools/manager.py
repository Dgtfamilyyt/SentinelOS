from tools.registry import TOOLS


class ToolManager:

    def execute(self, tool_name, *args, **kwargs):

        tool = TOOLS.get(tool_name)

        if tool is None:
            return f"Unknown tool: {tool_name}"

        return tool.execute(*args, **kwargs)

    def tool_names(self):

        return list(TOOLS.keys())

    def tool_metadata(self):

        metadata = []

        for tool in TOOLS.values():

            metadata.append({

                "name": tool.name,

                "category": tool.category,

                "description": tool.description,

                "parameters": tool.parameters,

                "safe": tool.safe

            })

        return metadata