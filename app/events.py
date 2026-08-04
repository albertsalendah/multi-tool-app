from __future__ import annotations

import logging
from collections import defaultdict
from threading import Lock
from typing import Callable, Any

log = logging.getLogger("MultiToolApp")


class EventBus:
    def __init__(self):
        self._listeners: dict[str, list[Callable[..., Any]]] = defaultdict(list)
        self._lock = Lock()

    def subscribe(self, event: str, callback: Callable[..., Any]):
        with self._lock:
            if callback not in self._listeners[event]:
                self._listeners[event].append(callback)

    def unsubscribe(self, event: str, callback: Callable[..., Any]):
        with self._lock:
            if callback in self._listeners[event]:
                self._listeners[event].remove(callback)

    def emit(self, event: str, **payload):
        # Snapshot under the lock, then run callbacks outside of it - a
        # listener that itself subscribes/unsubscribes/emits (reentrant)
        # would otherwise deadlock against a plain (non-reentrant) Lock.
        with self._lock:
            callbacks = list(self._listeners[event])

        for callback in callbacks:
            try:
                callback(**payload)
            except Exception:
                # One bad subscriber (e.g. a logging handler with a bug)
                # must not stop the remaining listeners from running, or
                # propagate back into whatever code path emitted this -
                # emit() is fire-and-forget from the caller's perspective.
                log.exception(
                    f"Listener for event '{event}' raised - continuing."
                )

    def clear(self):
        with self._lock:
            self._listeners.clear()
