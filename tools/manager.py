import importlib
import inspect
import pkgutil

from tools.base import Tool
from tools.registry import ToolRegistry
from tools.validator import ToolValidator

class ToolManager:

    def __init__(self):
        self.registry = ToolRegistry()
        self.validator = ToolValidator()

    def discover(self):

        import tools

        for _, module_name, _ in pkgutil.walk_packages(
            tools.__path__,
            tools.__name__ + "."
        ):

            try:
                module = importlib.import_module(module_name)

                for _, obj in inspect.getmembers(
                    module,
                    inspect.isclass
                ):

                    if (
                        issubclass(obj, Tool)
                        and obj is not Tool
                        and not inspect.isabstract(obj)
                    ):
                        tool = obj()
                        errors = self.validator.validate(tool)
                        if errors:
                            print(f"❌ Invalid tool: {obj.__name__}")
                            for error in errors:
                                print(f"  - {error}")

                            continue
                        self.registry.register(tool)

            except Exception as e:
                print(f"Failed to load {module_name}: {e}")

    def get(self, name):
        return self.registry.get(name)

    def all(self):
        return self.registry.all()