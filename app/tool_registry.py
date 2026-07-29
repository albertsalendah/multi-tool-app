from __future__ import annotations

import importlib
import inspect
import pkgutil
import json
from pathlib import Path

from app.plugin import PluginManifest

from tools import __path__ as tools_path
from tools.base_tool import BaseTool


class ToolRegistry:
    def __init__(self):
        self._tools = {}
        self._manifests: dict[str, PluginManifest] = {}

    def discover_tools(self):
        self._tools.clear()
        self._manifests.clear()

        for _, module_name, is_pkg in pkgutil.iter_modules(tools_path):
            if not is_pkg:
                continue

            tool_dir = Path(tools_path[0]) / module_name
            manifest_path = tool_dir / "manifest.json"

            if not manifest_path.exists():
                continue

            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = PluginManifest(**json.load(f))

            if not manifest.enabled:
                continue

            module_name_str, class_name = manifest.entry.split(":")

            module = importlib.import_module(f"tools.{module_name}.{module_name_str}")

            cls = getattr(module, class_name)

            if not issubclass(cls, BaseTool):
                continue

            tool = cls()

            self.register(tool)

            self._manifests[manifest.id] = manifest

    def get_manifest(self, tool_id: str):
        return self._manifests[tool_id]

    def list_manifests(self):
        return list(self._manifests.values())
    def register(self, tool: BaseTool):
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool: {tool.name}")

        self._tools[tool.name] = tool

    def unregister(self, name: str):
        self._tools.pop(name, None)

    def get_tool(self, name: str) -> BaseTool:
        return self._tools[name]

    def list_tools(self):
        return list(self._tools.keys())

    def list_tool_info(self):
        return [
            {
                "name": t.name,
                "version": t.version,
                "description": t.description,
            }
            for t in self._tools.values()
        ]
    def get_capabilities(self, tool_id: str):
        return self._manifests[tool_id].capabilities
