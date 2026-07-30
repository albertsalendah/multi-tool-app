"""
Tool Template

Copy this file (and manifest.json - see
docs/templates/plugin_manifest_template.json) into tools/<your_tool_name>/
to create a new plugin. Full walkthrough:
docs/guides/PLUGIN_DEVELOPER_GUIDE.md
"""

from tools.base_tool import BaseTool


class ExampleTool(BaseTool):
    name = "example_tool"
    version = "1.0.0"
    description = "One-line summary of what this tool does."

    def initialize(self, context=None):
        """Optional. Runs once per execution, before validate()/run().
        Acquire per-run resources here (temp dirs, client sessions).
        No-op by default."""
        pass

    def validate(self, request) -> bool:
        """Optional. `request` is the read-only mapping of kwargs this
        tool was invoked with. Return False to reject it - run() is
        skipped, but cleanup() still runs. Valid by default."""
        return True

    def run(self, *, context=None, **kwargs):
        """Required. Do the work and return a result.

        `context` is this run's ExecutionContext - use
        context.get_service(...) for shared platform services and
        context.raise_if_cancelled() at safe interruption points in
        long-running tools. Everything else the caller passed arrives
        in **kwargs.
        """
        raise NotImplementedError

    def cleanup(self, context=None):
        """Optional. Runs once per execution, after run() - always, even
        if validate() rejected the request or run() raised. Release
        whatever initialize() acquired. No-op by default."""
        pass
