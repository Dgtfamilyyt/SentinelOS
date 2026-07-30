from tools.manager import ToolManager

manager = ToolManager()

manager.discover()

print()

for tool in manager.all():

    print(tool.info())