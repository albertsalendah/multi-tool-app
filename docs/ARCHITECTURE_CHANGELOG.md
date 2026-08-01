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

### Browser Stack Decision: SeleniumBase
- Decided SeleniumBase over Playwright, since `libraries/captcha_manager`
  was already built assuming SeleniumBase's API (`sb.cdp.*`,
  `sb.solve_captcha()`) - aligning with that instead of fighting it.
- `app/browser_manager.py` rewritten from a Playwright
  Browser/BrowserContext model to `acquire()` / `release()` /
  `shutdown()`, matching what `docs/implementation/BROWSER_MANAGER.md`
  already (aspirationally) documented. SeleniumBase's `SB()` is a
  per-session context manager, not a shared browser process you can
  cheaply open sub-contexts from, so each `acquire()` starts a
  genuinely new session via `SB(...).__enter__()` / `.__exit__()` -
  confirmed valid against the real installed library, not assumed.
  No pooling yet - that's still the separate "Browser Pool" roadmap
  item, deliberately not pulled into this change.
- `kernel.py`: dropped the `browser.initialize()` call entirely -
  there's nothing to pre-launch anymore. `BrowserManager` now takes
  `default_headless` from config at construction time, matching how
  `Logger` already pulls primitive config values the same way.
- Playwright removed entirely: `requirements.txt`, and
  `Dockerfile`'s browser install step replaced with real Google Chrome
  (not Debian's Chromium build - `uc=True` undetected-chromedriver
  mode, used for CAPTCHA-solving, is calibrated against actual Chrome
  and is more detectable running on Chromium's different fingerprint)
  plus `seleniumbase install chromedriver`. **Not verified with a real
  Docker build** - no Docker daemon and no network access to
  `dl.google.com` from the sandbox this was built in. Best-informed
  effort based on documented SeleniumBase/Chrome deployment patterns;
  needs a real build to confirm.
- Also cleaned up while in the area: `router.py`'s stale "ENGINE
  SELECTION" comment implying a live Playwright/SeleniumBase choice
  (and referencing a `video_downloader.interactive_detector` module
  that doesn't exist in the current directory structure anyway).

### Web UI Reconciliation, Stage 2: Interactive/CAPTCHA Path
- New `tools/video_downloader_interactive/` package - a separate tool
  from `video_downloader`, not an action param on it, since the
  registry's plugin discovery is one-manifest-per-top-level-directory
  (`ToolRegistry.discover_tools()` looks for exactly one
  `manifest.json` per `tools/<name>/` package) and the two genuinely
  need different capabilities (`["network"]` vs `["browser", "network"]`).
- `pipeline.py` replaces `selenium_detector.py`'s
  `run_detection_pipeline`, which opened the browser, checked/waited
  for a CAPTCHA, then did nothing else - never extracted a stream,
  never returned anything, hung forever from the caller's perspective.
  The new version actually completes: `activate_cdp_mode()` -> `goto()`
  -> `CaptchaManager(sb).check()` -> raise if still blocked, else
  extract the stream and return a result. Two `raise_if_cancelled()`
  checkpoints (before the CAPTCHA check, before stream extraction) -
  DELETE /api/v1/jobs/{id} can interrupt between those, though not
  mid-CAPTCHA-wait, since that sleep happens inside
  `captcha_manager.py`'s own code, opaque to cancellation checks.
- `tool.py`: `initialize()` acquires a *visible* session
  (`headless=False` - a human needs to see the window for manual
  CAPTCHA solving) with `log_cdp=True` (required for
  `stream_extractor`'s network-log sniffing - confirmed against the
  real installed seleniumbase that this wasn't being set anywhere
  before, which is a second reason the old pipeline's stream
  extraction never had a chance of working even if it had been
  reached). Session is stored via `context.set_state("sb", ...)`, not
  on `self` - the registry keeps one shared tool instance across every
  execution, so per-run state on `self` would race if two interactive
  jobs ran concurrently (`JobManager`'s pool defaults to 4 workers).
- `stream_extractor.py` moved into the new package (only the
  interactive tool uses it now) with the stale
  `video_downloader.extractor` import fixed to
  `tools.video_downloader.extractor`. Also removed the silent
  import-time stub fallback that masked ImportError with fake data for
  the whole function - exactly the kind of thing that let this bug go
  unnoticed. The *runtime* fallback (yt-dlp fails to parse a stream URL
  we already found) was kept - that one's reasonable, not a bug.
- `tools/video_downloader/selenium_detector.py` deleted entirely -
  fully replaced, nothing imports it anymore.
- `router.py`'s bespoke `detect-interactive`/`session/{id}/status`
  routes removed (same pattern as removing `/info` in Stage 1) -
  `static/app.js`'s "Try generic detection" now calls
  `POST /api/v1/jobs` + polls `GET /api/v1/jobs/{id}`, same as any
  other job.
- Verified with real end-to-end HTTP calls against `main.py`'s actual
  app (no stubbing needed this time - the thing that used to require
  stubbing, `selenium_detector.py`, is gone): job creation reaches the
  real Kernel/Registry/Permission/JobManager path, `POST /tools/{name}/run`
  correctly refuses this tool (400, `browser` capability), and `GET
  /api/v1/tools` lists both tools with accurate capabilities.
  **Not verified**: a real browser actually launching. This sandbox has
  no Chrome binary; a real `acquire()` call reaches genuine
  seleniumbase driver-download code but behavior there was
  inconsistent (a fast 403 in one run, a 30+ second hang in another) -
  looks like this sandbox's network restrictions, not a code defect,
  but flagging plainly rather than implying it's proven.

### Current Focus
Open question raised while finishing Stage 2, not yet decided: should
tool executions get a wrapping timeout (`WorkflowStep` already has
one), so a stuck browser launch or other slow operation can't tie up a
`JobManager` worker thread indefinitely? No streaming/live-progress
endpoint exists yet either - the REST API and CLI are poll-only for
job status.

### Known Technical Debt
- ~~Fix JobManager submit race condition~~ - fixed: `submit()` was
  calling `executor.submit()` twice, running every background job
  twice over.
- ~~Add cooperative cancellation token~~ - done, see "Cancellation
  Token" above (this item was stale - the token already existed by the
  time it was still listed here).
- ~~`tools/video_downloader/router.py` bypasses `kernel.run_tool()`~~ -
  fixed, both paths now (fast in Stage 1, interactive in Stage 2).
- ~~Two unreconciled browser stacks~~ - resolved, see "Browser Stack
  Decision" above.
- ~~`video_downloader`/`selenium_detector.py` never resolves its
  session dict~~ - fixed, see "Web UI Reconciliation, Stage 2" above.
- ~~`stream_extractor.py`'s stale pre-migration import~~ - fixed, same
  section.
- ~~`libraries/captcha_manager` never actually exercised~~ - now
  exercised by `tools/video_downloader_interactive/pipeline.py`.
- Make Job updates thread-safe - `Job.status` / `.result` / `.error` /
  `.progress` are still set without a lock in `JobManager`.
- Add immutable job snapshots - still open. `GET /jobs/{id}` gives a
  read-only view at the API layer, but there's no internal immutable
  snapshot type.
- `tests/test_execution_context.py::test_kernel_passes_context_for_foreground_and_background_execution`
  fails - its `ContextTool` still expects `kwargs["services"]`, but
  `kernel.run_tool()` now only injects `context`, not `services`.
  Pre-existing from the platform-execution-foundation merge.
- `Dockerfile`'s Chrome/chromedriver install step is still unverified -
  see "Browser Stack Decision" above.
- Whether tool executions need a wrapping timeout - see Current Focus.
  Not implemented; needs a decision, not a unilateral default.
- `captcha_manager.py`'s manual-CAPTCHA wait is a single 120-second
  sleep then one recheck, not a poll loop - if a human solves it in 5
  seconds, `check()` still blocks for the full 120s before noticing.
  Deliberately not touched while fixing the video_downloader pipeline
  (out of scope - `captcha_manager` is a separate shared library with
  its own established behavior); noting it here since nobody had
  written it down before.

