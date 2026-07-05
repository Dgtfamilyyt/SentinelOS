from tools.manager import ToolManager


class Dispatcher:

    def __init__(self):
        self.tools = ToolManager()

    def dispatch(self, plan):

        action = plan.get("action")

        if action != "tool":
            return None

        tool = plan.get("tool")

        args = plan.get("args", {})

        if isinstance(args, dict):
            return self.tools.execute(tool, **args)

        elif isinstance(args, list):
            return self.tools.execute(tool, *args)

        return self.tools.execute(tool)