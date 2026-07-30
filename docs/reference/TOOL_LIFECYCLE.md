# Tool Lifecycle

## Standard Lifecycle
Every call to `kernel.run_tool()` runs the tool through this sequence
once **per execution** (not once at app startup / plugin discovery time):

1. `initialize(context)`
2. `validate(request)`
3. `run(*, context, **kwargs)` - skipped if `validate()` returns `False`
4. `cleanup(context)` - always runs, even if `validate()` rejected the
   request or `run()` raised

This applies to both foreground and background (`background=True`)
execution.

## Responsibilities
- `initialize()` - acquire per-run resources (temp dirs, client sessions).
  Optional, no-op by default.
- `validate()` - reject bad input before doing real work. Returning
  `False` raises `ToolValidationError` (`tools/base_tool.py`) and skips
  `run()`; `cleanup()` still fires. Optional, valid by default.
- `run()` - produce the result. Required.
- `cleanup()` - release whatever `initialize()` acquired. Runs
  unconditionally. Optional, no-op by default.

## Implementation
See `tools/base_tool.py` (`BaseTool`) for the concrete contract and
`docs/templates/tool_template.py` for a starting point.
