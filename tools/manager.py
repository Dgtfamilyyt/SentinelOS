import importlib
import pkgutil

from tools.registry import ToolRegistry


class ToolManager:

    def __init__(self):

        self.registry = ToolRegistry()

    def discover(self):

        import tools

        for _, module_name, _ in pkgutil.walk_packages(
            tools.__path__,
            tools.__name__ + "."
        ):

            try:

                module = importlib.import_module(module_name)

                if hasattr(module, "tool"):

                    self.registry.register(module.tool)

            except Exception as e:

                print(f"Failed to load {module_name}: {e}")

    def get(self, name):

        return self.registry.get(name)

    def all(self):

        return self.registry.all()