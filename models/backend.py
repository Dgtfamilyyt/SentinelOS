"""Provider-neutral model backend contract and Sentinel's local Ollama adapter."""

from __future__ import annotations


class ModelBackend:
    """Minimal transport interface; planning and agent behavior stay in Sentinel."""

    name = "backend"

    def generate(self, model, messages):
        raise NotImplementedError


class LocalOllamaBackend(ModelBackend):
    name = "ollama"

    def __init__(self, runtime, chat_function):
        self.runtime = runtime
        self.chat = chat_function

    def generate(self, model, messages):
        self.runtime.ensure_running()
        response = self.chat(model=model, messages=messages)
        return response["message"]["content"]
