# Plugin Developer Guide

## Purpose
Guide for creating new tools.

## Steps
1. Create `tools/<your_tool_name>/` with `__init__.py`, `tool.py`, and
   `manifest.json`.
2. Subclass `BaseTool` (`tools/base_tool.py`) in `tool.py` - start from
   `docs/templates/tool_template.py`.
3. Fill in `manifest.json` - start from
   `docs/templates/plugin_manifest_template.json`.
   - `entry` must be `"<module>:<ClassName>"` (e.g. `"tool:ExampleTool"`),
     matching the file/class from step 2.
   - `id` must match the `name` you set on your `BaseTool` subclass -
     the kernel looks up manifests by tool name for permission checks,
     and a mismatch means `run_tool()` can't find your manifest.
   - `capabilities` must use the values in `app/capabilities.py`
     (`Capability` enum) for any platform service your tool needs
     (`browser`, `network`, `filesystem`, etc).
4. Implement the lifecycle (see `docs/reference/TOOL_LIFECYCLE.md`):
   `initialize()` and `cleanup()` are optional, `validate()` is
   optional, `run()` is required.
5. Restart the kernel. Tools are discovered automatically from
   `tools/*/manifest.json` on `kernel.initialize()` - no manual
   registration step. A broken manifest or import error is logged and
   skipped rather than crashing discovery for every other tool.
6. Test your tool.

## Required Lifecycle
- `initialize(context)` - optional, no-op by default
- `validate(request)` - optional, returns `True` by default
- `run(*, context, **kwargs)` - required
- `cleanup(context)` - optional, no-op by default, always runs
