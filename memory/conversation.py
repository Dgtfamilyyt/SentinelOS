from ai.prompts import SYSTEM_PROMPT


class Conversation:

    def __init__(self):

        self.messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            }
        ]

    def add_user(self, prompt):

        self.messages.append(
            {
                "role": "user",
                "content": prompt
            }
        )

    def add_assistant(self, answer):

        self.messages.append(
            {
                "role": "assistant",
                "content": answer
            }
        )

    def get_messages(self):

        return self.messages

    def clear(self):

        self.messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            }
        ]