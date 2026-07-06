"""
===========================================
Sentinel OS
Model Registry
===========================================
"""

from models.profiles import MODELS


class ModelRegistry:

    def get(self, role):
        return MODELS.get(role)

    def all(self):
        return MODELS

    def roles(self):
        return list(MODELS.keys())

    def model_name(self, role):
        model = self.get(role)

        if model:
            return model["name"]

        return None