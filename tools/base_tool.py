from __future__ import annotations

from abc import ABC, abstractmethod


class BaseTool(ABC):
    name: str = ""
    version: str = "1.0.0"
    description: str = ""

    @abstractmethod
    def run(self, *, context=None, **kwargs):
        """Run the tool.

        ``context`` is an optional ExecutionContext supplied by the platform.
        Existing tools may continue to use ``services`` and other keyword
        arguments while they are migrated. Long-running tools should call
        ``context.raise_if_cancelled()`` at safe interruption points.
        """
        raise NotImplementedError
