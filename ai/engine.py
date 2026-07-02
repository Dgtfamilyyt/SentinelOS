from ollama import chat
from core.logger import logger
from ai.router import AIRouter
from memory.conversation import Conversation


class AIEngine:

    def __init__(self):

        self.router = AIRouter()

        self.conversation = Conversation()


    def ask(self, prompt):

        model = self.router.get_model(prompt)

        logger.info(f"Model Selected: {model}")
        

        self.conversation.add_user(prompt)

        response = chat(
            model=model,
            messages=self.conversation.get_messages()
        )

        answer = response.message.content
        
        logger.info("Response Generated")

        self.conversation.add_assistant(answer)

        return answer