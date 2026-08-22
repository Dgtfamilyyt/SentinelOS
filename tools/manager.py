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
                module = importlib.import_module(
                    module_name
                )

                for _, obj in inspect.getmembers(
                    module,
                    inspect.isclass
                ):

                    # Only classes actually defined
                    # inside this module.
                    if obj.__module__ != module.__name__:
                        continue

                    if (
                        issubclass(obj, Tool)
                        and obj is not Tool
                        and not inspect.isabstract(obj)
                    ):
                        tool = obj()

                        errors = (
                            self.validator.validate(tool)
                        )

                        if errors:
                            print(
                                f"Invalid tool: "
                                f"{obj.__name__}"
                            )

                            for error in errors:
                                print(
                                    f"   - {error}"
                                )

                            continue

                        self.registry.register(tool)

            except Exception as error:
                print(
                    f"Failed to load "
                    f"{module_name}: {error}"
                )

    def get(self, name):
        return self.registry.get(name)

    def all(self):
        return self.registry.all()

    def names(self):
        return self.registry.names()

    def execute(
        self,
        name,
        parameters=None
    ):
        tool = self.registry.get(name)

        if tool is None:
            return {
                "success": False,
                "error": (
                    f"Tool not found: {name}"
                )
            }

        prepared, errors = (
            self.validator.prepare_parameters(
                tool,
                parameters
            )
        )

        if errors:
            return {
                "success": False,
                "tool": name,
                "error": "Invalid parameters",
                "details": errors,
            }

        try:
            result = tool.execute(**prepared)

            return {
                "success": True,
                "tool": name,
                "result": result,
            }

        except Exception as error:
            return {
                "success": False,
                "tool": name,
                "error": str(error),
            }