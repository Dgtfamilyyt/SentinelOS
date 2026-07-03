from abc import ABC, abstractmethod


class Tool(ABC):
    """Base class for every Sentinel tool."""

    name = ""
    description = ""

    @abstractmethod
    def execute(self, *args, **kwargs):
        """Execute the tool."""
        pass