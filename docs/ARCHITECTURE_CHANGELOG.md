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
- CLI

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

### CLI
- Added an installable `multitool` console script (`pip install -e .`)
  built as a REST API client, not an in-process Kernel driver - it
  talks to a running server the same way the static UI does, rather
  than embedding the Kernel itself. Kept deliberately separate from
  `requirements.txt`/the server's dependency stack: the CLI only needs
  `httpx`, not `playwright`/`seleniumbase`/`yt-dlp`.
- Commands: `health`, `tools list`, `jobs create --tool NAME [--param
  KEY=VALUE...] [--wait]`, `jobs get JOB_ID`, `jobs cancel JOB_ID`.
- `jobs create --wait` polls `GET /jobs/{id}` until a terminal status -
  there's no streaming/SSE endpoint yet, so polling is what "wait for
  a job" means today.

### Web UI Reconciliation (fast path only - Stage 1)
- Added `POST /api/v1/tools/{name}/run`: runs a tool synchronously and
  returns its result directly, for fast tools where job creation +
  polling would be pure overhead. Refuses (400) any tool declaring the
  `browser` capability, since those can run long (e.g. manual CAPTCHA
  solving) - `POST /jobs` is for those.
- `VideoDownloaderTool.run()` was a stub (did nothing, returned
  `None`); it now actually calls `fetch_video_info()` and returns the
  result. Added `validate()` (rejects requests with no `url`).
  Narrowed its manifest's `capabilities` from
  `["browser", "network", "filesystem"]` to `["network"]` - the fast
  path touches neither a browser nor the filesystem.
- `static/app.js`'s "Fetch details" button now calls
  `POST /api/v1/tools/video_downloader/run` instead of the
  tool-specific `GET /tools/video-downloader/info`, which was removed
  from `router.py` as redundant.
- Found and fixed while touching `router.py`: `STATIC_DIR` was missing
  one `.parent` and pointed at the nonexistent `tools/static/`, so
  `GET /tools/video-downloader` (the page itself) 500'd on every
  request. Unrelated to this task's actual goal, just adjacent and
  broken.
- The interactive/CAPTCHA path (`detect-interactive`,
  `session/{id}/status`, the "Try generic detection" button) is
  untouched - still bypasses the Kernel, still broken exactly as
  before. That's Stage 2, see Current Focus and Known Technical Debt.

### Current Focus
Stage 2 of the web UI reconciliation: the interactive/CAPTCHA path.
Blocked on resolving Playwright vs. SeleniumBase first - see Known
Technical Debt. No streaming/live-progress endpoint exists yet - the
REST API and CLI are poll-only for job status.

### Known Technical Debt
- ~~Fix JobManager submit race condition~~ - fixed: `submit()` was
  calling `executor.submit()` twice, running every background job
  twice over.
- ~~Add cooperative cancellation token~~ - done, see "Cancellation
  Token" above (this item was stale - the token already existed by the
  time it was still listed here).
- ~~`tools/video_downloader/router.py` bypasses `kernel.run_tool()`~~ -
  fixed for the fast info-lookup path (see "Web UI Reconciliation"
  above). Still true for the interactive/CAPTCHA path - see the next
  few items, all still open.
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
  tool actually drives. This blocks Stage 2 and needs deciding first.
- `libraries/captcha_manager` is fully built but never registered as a
  platform service; `Capability.CAPTCHA` is currently a no-op
  permission check.

