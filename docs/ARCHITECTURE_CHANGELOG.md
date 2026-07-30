# Architecture Changelog

## 2026-07-30

### Initial Architecture
- Reorganized project structure.
- Added Application Kernel.

### Added
- Tool Registry
- Automatic Plugin Discovery
- Job Manager
- Browser Manager
- Event Bus
- Configuration System
- Logging System
- Service Container
- Plugin Manifest & Metadata System
- Capability & Permission System
- Shared Context / Execution Context
- Workflow Engine
- Workflow Events
- Plugin SDK
- REST API

### Shared Context / Execution Context
- Added a per-execution context with job and tool identity.
- Context exposes read-only request data, shared service access, and isolated thread-safe state.
- Context is available to foreground and background tool executions.

### Cancellation Token
- Added thread-safe, cooperative cancellation tokens for execution contexts.
- Job cancellation now signals running tools and preserves queued-job cancellation.

### Scheduler
- Added in-process one-time scheduling through the Job Manager.
- Scheduled executions can be inspected, cancelled, and stopped during kernel shutdown.

### Workflow Engine
- `ParallelGroup` executes its branches concurrently via a thread pool; every
  branch runs to completion even if a sibling fails, and all failures are
  raised together as one `WorkflowGroupError` once the group finishes.
- Fixed `WorkflowState` wiring (the engine previously referenced a
  `workflow.context` attribute that didn't exist).
- Node dispatch is recursive, so nested `ParallelGroup`s work even though
  the fluent `Workflow.parallel()` API doesn't expose nesting yet.

### Workflow Events
- `workflow.started` / `.progress` / `.completed` / `.failed` emitted via
  the existing Event Bus, with default logging subscriptions in the
  Kernel, same as `job.*` / `tool.*`.
- `workflow.progress` fires once per leaf step - including branches inside
  a `ParallelGroup`, via a thread-safe shared counter - not once per
  top-level node.

### Plugin SDK
- `BaseTool` now has a real per-execution lifecycle:
  `initialize() -> validate() -> run() -> cleanup()`. Previously only
  `run()` existed even though the docs described the full lifecycle.
  `cleanup()` always runs, even on a validation rejection or a `run()`
  failure.
- `ToolRegistry.discover_tools()` now isolates each plugin's load; a
  broken `manifest.json` or import error is logged and skipped instead
  of crashing discovery for every other tool.

### REST API
- Added `/api/v1` (`GET /health`, `GET /tools`, `POST /jobs`,
  `GET /jobs/{id}`, `DELETE /jobs/{id}`) as a generic, Kernel-backed
  router - any registered tool can be run as a background job through
  it without a bespoke per-tool router.
- `main.py` now has a real `app` object wired through a `lifespan`
  handler (Kernel init/shutdown). Previously `main.py` had no
  module-level `app` at all, so `Dockerfile`'s `CMD` (`uvicorn
  main:app`) would have failed to start the container as configured.

### Current Focus
Implement CLI, as a REST API client (talks to a running server over
HTTP; does not embed the Kernel in-process). Live progress is
poll-only for now (`GET /jobs/{id}`) - no streaming/SSE/WebSocket
endpoint exists yet.

### Known Technical Debt
- ~~Fix JobManager submit race condition~~ - fixed: `submit()` was
  calling `executor.submit()` twice, running every background job
  twice over.
- ~~Add cooperative cancellation token~~ - done, see "Cancellation
  Token" above (this item was stale - the token already existed by the
  time it was still listed here).
- Make Job updates thread-safe - `Job.status` / `.result` / `.error` /
  `.progress` are still set without a lock in `JobManager`.
- Add immutable job snapshots - still open. `GET /jobs/{id}` gives a
  read-only view at the API layer, but there's no internal immutable
  snapshot type.
- `tests/test_execution_context.py::test_kernel_passes_context_for_foreground_and_background_execution`
  fails - its `ContextTool` still expects `kwargs["services"]`, but
  `kernel.run_tool()` now only injects `context`, not `services`.
  Pre-existing from the platform-execution-foundation merge.
- `video_downloader` (`tools/video_downloader/selenium_detector.py`)
  never resolves its session dict on completion - the "Try generic
  detection" button hangs indefinitely.
- `tools/video_downloader/stream_extractor.py` imports from the
  pre-migration path `video_downloader.extractor` instead of
  `tools.video_downloader.extractor`; the import always fails and
  silently falls back to a stub.
- Two unreconciled browser stacks: `app/browser_manager.py`
  (Playwright) vs. `selenium_detector.py` (SeleniumBase) - neither
  `ExecutionContext.browser` nor `Capability.BROWSER` touches what the
  tool actually drives.
- `libraries/captcha_manager` is fully built but never registered as a
  platform service; `Capability.CAPTCHA` is currently a no-op
  permission check.
- `tools/video_downloader/router.py` bypasses `kernel.run_tool()`
  entirely, so the Execution Context / Permission / Job Manager layer
  (and now the REST API) is inert for the one real tool in the app.
  All of the above `video_downloader`-specific items are intentionally
  deferred until the platform framework itself is further along.
