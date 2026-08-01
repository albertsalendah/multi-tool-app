import app.tool_registry as tool_registry_module
from app.tool_registry import ToolRegistry


def test_discover_tools_skips_a_broken_plugin_without_crashing():
    registry = ToolRegistry()
    calls = []

    def fake_iter_modules(path):
        return [
            (None, "broken_tool", True),
            (None, "good_tool", True),
            (None, "not_a_package", False),  # ignored, is_pkg=False
        ]

    def fake_load_tool(self, module_name):
        calls.append(module_name)
        if module_name == "broken_tool":
            raise ValueError("malformed manifest.json")
        self._tools[module_name] = object()

    original_iter_modules = tool_registry_module.pkgutil.iter_modules
    original_load_tool = ToolRegistry._load_tool

    tool_registry_module.pkgutil.iter_modules = fake_iter_modules
    ToolRegistry._load_tool = fake_load_tool

    try:
        registry.discover_tools()
    finally:
        tool_registry_module.pkgutil.iter_modules = original_iter_modules
        ToolRegistry._load_tool = original_load_tool

    # Both modules were attempted despite the first one failing...
    assert calls == ["broken_tool", "good_tool"]
    # ...and the failure didn't stop the second one from registering.
    assert "good_tool" in registry._tools
    assert "broken_tool" not in registry._tools


def test_real_video_downloader_manifest_still_loads():
    """Regression check: the actual manifest.json/tool.py in the repo
    still discover correctly after the resilience refactor."""
    registry = ToolRegistry()
    registry.discover_tools()

    assert "video_downloader" in registry.list_tools()
    manifest = registry.get_manifest("video_downloader")
    assert manifest.entry == "tool:VideoDownloaderTool"
    assert manifest.capabilities == ["network"]


def test_real_video_downloader_interactive_manifest_loads():
    """Regression check for the new interactive/CAPTCHA tool - real
    discovery, not mocked, confirming the second manifest.json in
    tools/ doesn't collide with or break discovery of the first."""
    registry = ToolRegistry()
    registry.discover_tools()

    assert "video_downloader_interactive" in registry.list_tools()
    manifest = registry.get_manifest("video_downloader_interactive")
    assert manifest.entry == "tool:VideoDownloaderInteractiveTool"
    assert manifest.capabilities == ["browser", "network"]
    assert len(registry.list_tools()) == 2
