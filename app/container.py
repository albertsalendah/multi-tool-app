from __future__ import annotations

from threading import Lock


class ServiceContainer:
    def __init__(self):
        self._services = {}
        self._lock = Lock()

    def register(self, name: str, service):
        with self._lock:
            if name in self._services:
                raise ValueError(f"Service '{name}' already registered.")

            self._services[name] = service

    def unregister(self, name: str):
        with self._lock:
            self._services.pop(name, None)

    def get(self, name: str):
        with self._lock:
            if name not in self._services:
                raise KeyError(f"Service '{name}' not found.")

            return self._services[name]

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._services

    def list_services(self):
        with self._lock:
            return list(self._services.keys())
