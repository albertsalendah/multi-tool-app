from __future__ import annotations

from threading import Event


class CancellationRequested(RuntimeError):
    """Raised when a cooperative execution observes cancellation."""


class CancellationToken:
    """Thread-safe cancellation signal for a single execution."""

    def __init__(self):
        self._cancelled = Event()

    def cancel(self) -> bool:
        if self._cancelled.is_set():
            return False

        self._cancelled.set()
        return True

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._cancelled.wait(timeout)

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise CancellationRequested("Execution was cancelled.")
