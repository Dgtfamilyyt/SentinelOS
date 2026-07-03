from tools.manager import ToolManager

manager = ToolManager()

print(manager.available_tools())

print(manager.execute("current_directory"))