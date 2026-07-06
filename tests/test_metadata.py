from tools.manager import ToolManager

manager = ToolManager()

for tool in manager.tool_metadata():

    print(tool)