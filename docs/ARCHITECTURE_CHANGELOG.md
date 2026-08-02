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

### Full Platform Audit
Requested explicitly: review everything outside video_downloader/
CAPTCHA specifics (those are deliberately deferred - see "Next
Milestones" in `docs/STATUS.md`) for anything missed or improvable.
Read every `app/` module, `cli/`, `main.py`, `tools/base_tool.py`
fresh, and cross-checked docs against real code rather than relying on
memory. Findings, by severity - fixed ones marked, everything else
still open:

**Real bugs (confirmed by reproduction, not theoretical):**
- ~~`Config.get()` doesn't type-coerce environment variable
  overrides~~ - NOT fixed this round (out of the "minor" batch that
  was fixed - see below). Confirmed concretely: `JOBS_MAX_WORKERS=8`
  crashes kernel construction (`TypeError`, comparing `str` to `int`
  inside `ThreadPoolExecutor`); `BROWSER_HEADLESS=false` silently does
  the *opposite* of what's intended (non-empty string is truthy, so
  headless stays `True`). Still open.
- `tool.finished` event never fires for background jobs - only the
  synchronous path in `kernel.run_tool()` emits it. Since background
  execution is the primary path now, anything built on `tool.finished`
  for logging/monitoring would silently miss most executions. Still open.
- `context.report_progress()` is completely disconnected from
  `job.progress` - a tool can call it, but `GET /api/v1/jobs/{id}`'s
  `progress` field reads from a separate `Job.progress` attribute
  nothing ever updates mid-run. Shows `0` the whole time, then jumps to
  `100` on completion regardless of what a tool reports. Still open.
- `POST /tools/{name}/run`'s error handling can misclassify a tool's
  own internal `KeyError` bug as `"Unknown tool"` (404) - the
  `except KeyError` wraps the whole `kernel.run_tool()` call, including
  the tool's own `run()`. Still open (not part of the fixed batch -
  fixing it means narrowing that except clause, deliberately left for
  next time since it wasn't in the requested 15-20 list).
- ~~`main.py`'s comment above `include_router(video_downloader_router)`
  claims it "still bypasses the kernel directly"~~ - **still stale,
  not fixed this round** (also wasn't in the requested batch). True
  when written (Stage 1 commit), false since Stage 2. Quick fix
  whenever someone's next in that file.

**Security (not addressed this round - explicitly bigger than "minor"):**
- No authentication anywhere on the REST API - anyone who can reach it
  can run any tool, including the one that launches a real browser.
- CORS is wide open (`allow_origins=["*"]` + `allow_credentials=True`
  in `main.py`) - any website's JS can hit the local API with
  credentials if the browser can reach it. Meaningful combined with
  the point above, not just theoretical.

**Design/scale gaps (not bugs, real capacity/capability gaps):**
- `JobManager._jobs` / `Scheduler._schedules` grow forever - no
  cleanup, eviction, or archival. Unbounded memory growth on a
  long-running server. (`JOB_LIFECYCLE.md` documents a "Job Archived"
  state that was never built.)
- `JobManager.shutdown()` calls `executor.shutdown(wait=True)` - blocks
  indefinitely if any job is stuck. Not just "the job never finishes" -
  the whole app can't shut down gracefully either. The new
  `BrowserManager` watchdog (below) helps for browser-specific hangs
  but doesn't touch this generally.
- `Scheduler` is fully built, tested, wired into the kernel - and has
  zero REST/CLI surface. Currently unreachable from outside the process.
- `GET /api/v1/tools` doesn't expose a tool's `capabilities` - no way
  for a caller to know a tool needs `browser` (and might run long)
  without trying it and getting refused, or reading source.
- `ToolRegistry` reuses one shared tool instance across every
  execution, forever. Handled correctly for the interactive tool via
  `context.set_state()`, but it's a footgun for any future tool author
  who stores state on `self` instead.
- `EventBus.emit()` doesn't isolate listener failures (one bad
  subscriber breaks the rest, and whatever called `emit()`), and
  neither it nor `ServiceContainer` has any locking. Low practical risk
  today (all current listeners are simple `log.info()` calls), worth
  knowing as the app grows.
- `PermissionManager` only really enforces the `browser` capability -
  `network`/`filesystem`/`captcha`/`clipboard`/`database` are
  declared-but-unchecked (map to `None` in `_services`). Worth
  confirming this is intentional rather than assumed-done.

**Minor - six of these were fixed this round, see below for which.**

### BrowserManager: PID Tracking + Watchdog
Concrete fix for the "stuck browser hang" case discussed at length
(threads can't be killed from outside; a timeout on the caller's side
doesn't free the underlying thread/process - see the earlier
conversation about this before assuming a naive timeout would be enough).

- `acquire(timeout=..., **overrides)`: if `timeout` is given, a
  `threading.Timer` starts immediately. If the session isn't
  `release()`'d within that many seconds, its real OS-level browser
  process is force-killed (`SIGKILL`) and the session is torn down
  automatically. `timeout=None` (default) - identical behavior to
  before, nothing changes for existing callers.
- PID resolution (`_resolve_pid()`) confirmed against the real
  installed `seleniumbase`/`selenium` packages, not guessed:
  `driver.browser_pid` for `uc=True` sessions (SeleniumBase's own
  internal cleanup uses this exact attribute the same way -
  `os.kill(self.browser_pid, 15)` in `seleniumbase/undetected/__init__.py`
  - so this is a real, supported mechanism), falling back to
  `driver.service.process.pid` (standard Selenium `Service` API) for
  non-`uc` sessions.
  `release()` cancels any outstanding watchdog. `shutdown()` cancels
  all outstanding watchdogs before its normal cleanup sweep.
- Tests use real, self-controlled subprocesses (`sleep 100`, killed via
  the actual manager) rather than mocking `os.kill` - proves the kill
  mechanism genuinely works end-to-end, not just that a function got
  called.
- Deliberately scoped to `BrowserManager` only. NOT wired into
  `video_downloader_interactive`'s `initialize()` yet - that's a
  video_downloader-specific change, still deferred per the person's
  explicit request. Does NOT answer the general "should tool
  executions get a wrapping timeout" question either - that's a
  broader design decision this doesn't resolve, just makes the
  browser-specific case concretely fixable once someone opts a tool
  into it.

### Current Focus
Nothing actively in progress. Two undecided items carried forward,
most consequential first:
1. General tool-execution timeout - separate from the BrowserManager
   watchdog above, which only helps once a tool actually calls
   `acquire(timeout=...)`. Nothing calls it with a timeout yet.
2. No authentication on the REST API - low risk while local-only, real
   risk the moment this is exposed beyond one machine.

Also still true: no streaming/live-progress endpoint - the REST API
and CLI are poll-only for job status.

### Known Technical Debt
Fixed this round (six "minor" items, explicitly requested as a batch):
- ~~`logs/app.log` not in `.gitignore`~~ - added `logs/*.log`. Was
  manually `rm`'d before every commit all session; one missed removal
  away from landing in git history.
- ~~`Config` does zero validation~~ - a missing config file now logs a
  warning and falls back to defaults instead of silently continuing; a
  malformed one logs a warning and falls back instead of crashing with
  a raw YAML traceback. (Note: this is about the file itself being
  readable/parseable - it does NOT fix the separate, still-open
  env-var type-coercion bug above.)
- ~~`CONFIGURATION_SCHEMA.md` documents sections that don't exist~~ -
  corrected to list real sections (`app`/`browser`/`jobs`/`logging`)
  separately from planned ones.
- ~~`ERROR_CODES.md`'s codes never used anywhere~~ - marked explicitly
  as planned/not-yet-implemented rather than implying they're live.
- ~~Unused `import inspect` in `app/tool_registry.py`~~ - removed.
- ~~`POST /api/v1/jobs` / `POST /tools/{name}/run` don't guard against
  `params` colliding with `run_tool()`'s own `name`/`background`
  arguments~~ - both now reject with a clean 400 instead of an
  unhandled 500.

Still open (carried forward from before, plus everything found in this
audit that wasn't in the fixed batch - see "Full Platform Audit" above
for the complete list with detail):
- ~~Fix JobManager submit race condition~~ - fixed (earlier round):
  `submit()` was calling `executor.submit()` twice.
- ~~Add cooperative cancellation token~~ - done (earlier round).
- ~~`tools/video_downloader/router.py` bypasses `kernel.run_tool()`~~ -
  fixed (earlier round), both paths.
- ~~Two unreconciled browser stacks~~ - resolved (earlier round).
- ~~`video_downloader`/`selenium_detector.py` never resolves its
  session dict~~ - fixed (earlier round).
- ~~`stream_extractor.py`'s stale pre-migration import~~ - fixed
  (earlier round).
- ~~`libraries/captcha_manager` never actually exercised~~ - now
  exercised by `tools/video_downloader_interactive/pipeline.py`.
- `Config.get()` env-var overrides aren't type-coerced (crashes for
  ints, silently wrong for bools) - see "Full Platform Audit."
- `tool.finished` never fires for background jobs - see "Full Platform Audit."
- `context.report_progress()` disconnected from `job.progress` - see
  "Full Platform Audit."
- `POST /tools/{name}/run`'s `KeyError` handling can misclassify a
  tool's own internal bug as "Unknown tool" - see "Full Platform Audit."
- `main.py`'s stale comment about video_downloader_router still
  bypassing the kernel - see "Full Platform Audit."
- No authentication on the REST API; CORS wide open - see "Full
  Platform Audit" / Current Focus.
- `JobManager`/`Scheduler` never clean up old entries; no
  general tool-execution timeout; `Scheduler` has no REST/CLI surface;
  `GET /api/v1/tools` doesn't expose capabilities; shared tool
  instances are a footgun for future tool authors; `EventBus`/
  `ServiceContainer` have no locking or listener isolation;
  `PermissionManager` only enforces `browser` - see "Full Platform
  Audit" for detail on all of these.
- Make Job updates thread-safe - `Job.status` / `.result` / `.error` /
  `.progress` are still set without a lock in `JobManager`.
- Add immutable job snapshots - `GET /jobs/{id}` gives a read-only view
  at the API layer, but there's no internal immutable snapshot type.
- `tests/test_execution_context.py::test_kernel_passes_context_for_foreground_and_background_execution`
  fails - its `ContextTool` still expects `kwargs["services"]`, but
  `kernel.run_tool()` now only injects `context`. Pre-existing from the
  platform-execution-foundation merge, never fixed since nothing else
  touches that path.
- `Dockerfile`'s Chrome/chromedriver install step is still unverified -
  no Docker daemon available to test it.
- `captcha_manager.py`'s manual-CAPTCHA wait is a flat 120-second block,
  not a poll loop - deliberately not touched (separate shared library,
  video_downloader/CAPTCHA work is deferred).


