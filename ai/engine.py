from core.logger import logger
from memory.conversation import Conversation
from models.router import ModelRouter
from ai.client import AIClient


class AIEngine:

    def __init__(self):
        self.router = ModelRouter()
        self.client = AIClient()
        self.conversation = Conversation()

    def ask(self, prompt, task="chat"):
        model = self.router.choose(task)

        logger.info(f"Task: {task}")
        logger.info(f"Model Selected: {model}")

        self.conversation.add_user(prompt)

        answer = self.client.generate(
            model=model,
            messages=self.conversation.get_messages()
        )

        logger.info("Response Generated")

        self.conversation.add_assistant(answer)

        return answer