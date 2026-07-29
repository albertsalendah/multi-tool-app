from __future__ import annotations

from collections import defaultdict
from typing import Callable, Any


class EventBus:
    def __init__(self):
        self._listeners: dict[str, list[Callable[..., Any]]] = defaultdict(list)

    def subscribe(self, event: str, callback: Callable[..., Any]):
        if callback not in self._listeners[event]:
            self._listeners[event].append(callback)

    def unsubscribe(self, event: str, callback: Callable[..., Any]):
        if callback in self._listeners[event]:
            self._listeners[event].remove(callback)

    def emit(self, event: str, **payload):
        for callback in list(self._listeners[event]):
            callback(**payload)

    def clear(self):
        self._listeners.clear()