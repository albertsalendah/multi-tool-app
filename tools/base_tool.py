from __future__ import annotations

from abc import ABC, abstractmethod


class ToolValidationError(RuntimeError):
    """Raised by the kernel when a tool's validate() rejects a request."""


class BaseTool(ABC):
    name: str = ""
    version: str = "1.0.0"
    description: str = ""

    def initialize(self, context=None) -> None:
        """Called once per execution, before validate()/run().

        Override to acquire per-run resources (a temp directory, a client
        session, etc). Receives the same ExecutionContext that run() gets,
        so setup can be tied to this specific job rather than the tool's
        whole lifetime. No-op by default.
        """
        pass

    def validate(self, request) -> bool:
        """Called once per execution, after initialize() and before run().

        ``request`` is the read-only mapping of kwargs the tool was invoked
        with (ExecutionContext.request). Return False to reject the
        request - run() is skipped, but cleanup() still runs. Everything
        is considered valid by default.
        """
        return True

    @abstractmethod
    def run(self, *, context=None, **kwargs):
        """Run the tool.

        ``context`` is an optional ExecutionContext supplied by the platform.
        Existing tools may continue to use ``services`` and other keyword
        arguments while they are migrated. Long-running tools should call
        ``context.raise_if_cancelled()`` at safe interruption points.
        """
        raise NotImplementedError

    def cleanup(self, context=None) -> None:
        """Called once per execution, after run() - always, even if
        validate() rejected the request or run() raised.

        Override to release whatever initialize() acquired. No-op by
        default.
        """
        pass
