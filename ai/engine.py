from core.logger import logger
from ai.client import AIClient
from ai.prompts import SYSTEM_PROMPT
from ai.modes import get_mode_prompt
from models.router import ModelRouter


class AIEngine:

    def __init__(self):
        self.router = ModelRouter()
        self.client = AIClient()

        self.history = []

    def ask(self, prompt, task="chat"):

        model = self.router.choose(task)

        logger.info(f"Task: {task}")
        logger.info(f"Model Selected: {model}")

        mode_prompt = get_mode_prompt(task)

        messages = [
            {
                "role": "system",
                "content": (
                    SYSTEM_PROMPT
                    + "\n\n"
                    + mode_prompt
                )
            }
        ]

        messages.extend(self.history)

        messages.append(
            {
                "role": "user",
                "content": prompt
            }
        )

        answer = self.client.generate(
            model=model,
            messages=messages
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