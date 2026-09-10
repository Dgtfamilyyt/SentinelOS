from abc import ABC, abstractmethod

from tools.policy import PermissionClass


class Tool(ABC):
    """
    Base class for every Sentinel tool.
    """

    name = ""
    description = ""
    category = ""

    parameters = {}

    # New tools fail closed until they declare a less
    # restrictive execution classification.
    permission = PermissionClass.RESTRICTED

    @abstractmethod
    def execute(self, **kwargs):
        pass

    def info(self):
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "parameters": self.parameters,
            "permission": (
                self.permission.value
                if isinstance(
                    self.permission,
                    PermissionClass
                )
                else "UNKNOWN"
            ),
        }
