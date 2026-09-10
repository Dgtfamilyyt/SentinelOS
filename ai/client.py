from ollama import chat

from ai.ollama_runtime import get_ollama_runtime

class AIClient:

    def __init__(self, runtime=None):
        self.runtime = (
            runtime
            if runtime is not None
            else get_ollama_runtime()
        )

    def generate(self, model, messages):

        self.runtime.ensure_running()

        response = chat(
            model=model,
            messages=messages
        )

        return response["message"]["content"]
