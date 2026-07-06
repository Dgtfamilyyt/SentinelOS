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

        task = task.lower()

        if task in [
            "chat",
            "math",
            "general"
        ]:
            return self.registry.model_name("general")

        elif task in [
            "planning",
            "coding",
            "tool"
        ]:
            return self.registry.model_name("planner")

        elif task in [
            "cyber",
            "security",
            "malware"
        ]:
            return self.registry.model_name("cyber")

        return self.registry.model_name("deep")