"""
===========================================
Sentinel OS
Model Router
===========================================
"""

from models.registry import ModelRegistry


class ModelRouter:

    def __init__(self):
        self.registry = ModelRegistry()

    def choose(self, task):

        task = task.lower().strip()

        if task in [
            "chat",
            "math",
            "general",
        ]:
            return self.registry.model_name(
                "general"
            )

        if task in [
            "planning",
            "coding",
            "tool",
        ]:
            return self.registry.model_name(
                "planner"
            )

        if task in [
            "cyber",
            "security",
            "malware",

            # Sentinel security modes
            "red",
            "soc",
            "blue",
            "purple",
        ]:
            return self.registry.model_name(
                "cyber"
            )

        return self.registry.model_name(
            "deep"
        )