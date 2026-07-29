from __future__ import annotations

import importlib
import inspect
import pkgutil

from tools import __path__ as tools_path
from tools.base_tool import BaseTool


class ToolRegistry:
    def __init__(self):
        self._tools = {}

    def discover_tools(self):
        self._tools.clear()

        for _, module_name, is_pkg in pkgutil.iter_modules(tools_path):
            if not is_pkg:
                continue

            try:
                module = importlib.import_module(
                    f"tools.{module_name}.tool"
                )
            except ModuleNotFoundError:
                continue

            for _, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, BaseTool)
                    and obj is not BaseTool
                ):
                    instance = obj()
                    self.register(instance)

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