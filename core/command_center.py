from ai.engine import AIEngine
from ai.intent import IntentEngine
from tools.manager import ToolManager


class CommandCenter:

    def __init__(self):

        self.ai = AIEngine()
        self.intent = IntentEngine()
        self.tools = ToolManager()

    def process(self, prompt):

        intent = self.intent.classify(prompt)

        if intent["type"] == "tool":

            return self.tools.execute(
                intent["tool"],
                *intent["args"]
            )

        return self.ai.ask(prompt)