"""
===========================================
Sentinel OS
Module: Base Tool

Author: DGT

Purpose:
Defines the base class for every tool.
===========================================
"""

from abc import ABC, abstractmethod


class Tool(ABC):

    # Metadata
    name = ""
    category = ""
    description = ""
    parameters = []
    safe = True

    @abstractmethod
    def execute(self, *args, **kwargs):
        pass