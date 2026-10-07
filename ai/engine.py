from core.logger import logger
from ai.client import AIClient
from ai.prompts import SYSTEM_PROMPT
from ai.modes import get_mode_prompt
from models.router import ModelRouter
from contextlib import aclosing
from ai.streaming import bounded_messages, stream_model


class AIEngine:

    def __init__(self):
        self.router = ModelRouter()
        self.client = AIClient(router=self.router)

        self.history = []

    def ask(self, prompt, task="chat"):

        route = self.router.resolve(task)
        model = route.model

        logger.info(f"Task: {task}")
        logger.info(f"Model Selected: {model}")

        mode_prompt = get_mode_prompt(task)

        messages = bounded_messages(SYSTEM_PROMPT + "\n\n" + mode_prompt, self.history, prompt)

        answer = self.client.generate(
            model=model,
            messages=messages,
            task=task,
            route=route,
        )

        self.history.append(
            {
                "role": "user",
                "content": prompt
            }
        )

        self.history.append(
            {
                "role": "assistant",
                "content": answer
            }
        )

        logger.info(
            f"Response generated in {task} mode"
        )

        return answer

    def clear(self):
        self.history.clear()

    async def ask_stream(self, prompt, *, task, history, memories, model, runtime):
        route = self.router.resolve(task, model)
        selected = route.model
        system = SYSTEM_PROMPT + "\n\n" + get_mode_prompt(task)
        messages = bounded_messages(system, history, prompt, memories)
        async with aclosing(stream_model(runtime, selected, messages, route=route)) as events:
            async for event in events:
                yield event
