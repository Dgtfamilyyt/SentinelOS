from abc import ABC, abstractmethod


class Tool(ABC):
    """
    Base class for every Sentinel tool.
    """

    name = ""
    description = ""
    category = ""

    parameters = {}

    @abstractmethod
    def execute(self, **kwargs):
        pass

    def info(self):
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "parameters": self.parameters,
        }