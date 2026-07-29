from __future__ import annotations


class ServiceContainer:
    def __init__(self):
        self._services = {}

    def register(self, name: str, service):
        if name in self._services:
            raise ValueError(f"Service '{name}' already registered.")

        self._services[name] = service

    def unregister(self, name: str):
        self._services.pop(name, None)

    def get(self, name: str):
        if name not in self._services:
            raise KeyError(f"Service '{name}' not found.")

        return self._services[name]

    def has(self, name: str) -> bool:
        return name in self._services

    def list_services(self):
        return list(self._services.keys())
