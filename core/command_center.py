from ai.engine import AIEngine
from ai.intent import IntentEngine
from ai.dispatcher import Dispatcher
from tools.manager import ToolManager


class CommandCenter:

    def __init__(self):

        self.ai = AIEngine()
        self.intent = IntentEngine()

        self.tools = ToolManager()
        self.tools.discover()

        self.dispatcher = Dispatcher(
            ai_engine=self.ai,
            tool_manager=self.tools
        )

    def process(self, prompt):

        intent = self.intent.classify(prompt)

        return self.dispatcher.dispatch(
            prompt,
            intent
        )