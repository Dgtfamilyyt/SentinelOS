"""
===========================================
Sentinel OS
Model Registry
===========================================
"""

from models.profiles import MODELS


class ModelRegistry:

    def __init__(self):
        self._overrides = {}

    def set_role_model(self, role, model_name):
        self._overrides[role] = model_name

    def get(self, role):
        base = MODELS.get(role)
        if base and role in self._overrides:
            updated = dict(base)
            updated["name"] = self._overrides[role]
            return updated
        return base

    def all(self):
        if not self._overrides:
            return MODELS
        result = {}
        for role, profile in MODELS.items():
            if role in self._overrides:
                p = dict(profile)
                p["name"] = self._overrides[role]
                result[role] = p
            else:
                result[role] = profile
        return result

    def roles(self):
        return list(MODELS.keys())

    def model_name(self, role):
        if role in self._overrides:
            return self._overrides[role]
        model = self.get(role)
        if model:
            return model["name"]
        return None
