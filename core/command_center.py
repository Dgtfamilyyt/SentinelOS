from ai.engine import AIEngine
from ai.planner import Planner
from ai.dispatcher import Dispatcher
from tools.manager import ToolManager


class CommandCenter:

    def __init__(self):

        self.ai = AIEngine()

        self.tools = ToolManager()
        self.tools.discover()

        self.planner = Planner(
            tool_manager=self.tools
        )

        self.dispatcher = Dispatcher(
            ai_engine=self.ai,
            tool_manager=self.tools
        )

    def process(self, prompt):

        plan = self.planner.plan(
            prompt
        )

        return self.dispatcher.dispatch(
            prompt,
            plan
        )