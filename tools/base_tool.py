from __future__ import annotations

from abc import ABC, abstractmethod


class BaseTool(ABC):
    name: str = ""
    version: str = "1.0.0"
    description: str = ""

    @abstractmethod
    def run(self, **kwargs):
        pass