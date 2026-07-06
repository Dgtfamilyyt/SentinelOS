from ollama import chat

class AIClient:

    def generate(self, model, messages):

        response = chat(
            model=model,
            messages=messages
        )

        return response["message"]["content"]