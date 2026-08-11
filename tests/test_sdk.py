from tools.manager import ToolManager

manager = ToolManager()

manager.discover()

print()

for tool in manager.all():

    print(tool.info())

print("\nTesting tool execution...")

result = manager.execute(
    "current_directory"
)

print(result)

result = manager.execute(
    "list_files",
    {"path": "."}
)

print(result)
print("\nTesting invalid parameters...")

result = manager.execute(
    "list_files",
    {}
)

print(result)