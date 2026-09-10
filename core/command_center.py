from ai.engine import AIEngine
from ai.planner import Planner
from ai.dispatcher import Dispatcher
from tools.manager import ToolManager
from contextlib import aclosing


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

    async def process_stream(self, prompt, *, history, memories, model, runtime):
        plan = None
        async with aclosing(self.planner.plan_stream(prompt, runtime, model=model)) as events:
            async for event in events:
                if event["type"] == "plan":
                    plan = event["plan"]
                else:
                    yield event
        async with aclosing(self.dispatcher.dispatch_stream(
            prompt, plan, history=history, memories=memories, model=model, runtime=runtime
        )) as events:
            async for event in events:
                yield event
