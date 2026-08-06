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
All five fixed 2026-08-04 - see "Real Bugs Fixed" below for detail.
- ~~`Config.get()` doesn't type-coerce environment variable
  overrides~~ - fixed. `JOBS_MAX_WORKERS=8` crashed kernel construction
  (`TypeError`, comparing `str` to `int` inside `ThreadPoolExecutor`);
  `BROWSER_HEADLESS=false` silently did the *opposite* of what's
  intended (non-empty string is truthy, so headless stayed `True`).
- ~~`tool.finished` event never fires for background jobs~~ - fixed.
  Only the synchronous path in `kernel.run_tool()` used to emit it.
- ~~`context.report_progress()` is completely disconnected from
  `job.progress`~~ - fixed. Used to show `0` the whole run, then jump
  to `100` on completion regardless of what a tool reported.
- ~~`POST /tools/{name}/run`'s error handling can misclassify a tool's
  own internal `KeyError` bug as `"Unknown tool"` (404)~~ - fixed.
- ~~`main.py`'s comment above `include_router(video_downloader_router)`
  claims it "still bypasses the kernel directly"~~ - fixed (was true
  when written pre-Stage-2, stale since).

**Security (not addressed this round - explicitly bigger than "minor"):**
- No authentication anywhere on the REST API - anyone who can reach it
  can run any tool, including the one that launches a real browser.
- CORS is wide open (`allow_origins=["*"]` + `allow_credentials=True`
  in `main.py`) - any website's JS can hit the local API with
  credentials if the browser can reach it. Meaningful combined with
  the point above, not just theoretical.

**Design/scale gaps (not bugs, real capacity/capability gaps):**
- ~~`JobManager._jobs` grows forever - no cleanup, eviction, or
  archival~~ - fixed 2026-08-04 for `JobManager` specifically (TTL +
  max-count eviction of completed jobs). `Scheduler._schedules` has the
  same issue - fixed 2026-08-05, see "Scheduler Cleanup + REST/CLI
  Surface" below. (`JOB_LIFECYCLE.md` documents a "Job Archived" state
  that was never built.)
- ~~`JobManager.shutdown()` calls `executor.shutdown(wait=True)` -
  blocks indefinitely if any job is stuck~~ - fixed 2026-08-05, see
  "JobManager.shutdown() Bounded Wait" below. Note: this doesn't touch
  `Scheduler.shutdown()`, which never blocked on long-running work in
  the first place (it only cancels pending `Timer`s).
- ~~`Scheduler` is fully built, tested, wired into the kernel - and had
  zero REST/CLI surface~~ - fixed 2026-08-05, see "Scheduler Cleanup +
  REST/CLI Surface" below.
- ~~`GET /api/v1/tools` doesn't expose a tool's `capabilities`~~ - fixed
  2026-08-04.
- ~~`ToolRegistry` reuses one shared tool instance across every
  execution, forever~~ - fixed 2026-08-05, see "ToolRegistry Per-
  Execution Instances + PermissionManager Documentation" below.
- ~~`EventBus.emit()` doesn't isolate listener failures, and neither it
  nor `ServiceContainer` has any locking~~ - fixed 2026-08-04.
- `PermissionManager` only really enforces the `browser` capability -
  documented 2026-08-05 as an intentional boundary, not fixed as
  "real enforcement" (there's nothing meaningful to enforce for
  `network`/`filesystem`, and no backing service yet for
  `clipboard`/`database`/`captcha`) - see "ToolRegistry Per-Execution
  Instances + PermissionManager Documentation" below.

**Minor - six of these were fixed this round, see below for which.**

### Design/Scale Gaps Fixed (2026-08-04)
Three of the six items above, plus the two Job thread-safety items from
Known Technical Debt below. Security, and the remaining three
Design/scale gaps (JobManager.shutdown() blocking, Scheduler's missing
REST/CLI surface, ToolRegistry's shared-instance footgun,
PermissionManager's partial enforcement), stay open - the person
explicitly deferred Security and said "straightforward ones" plus
JobManager cleanup for this round, not the ones needing a design call.

- `app/tool_registry.py`: `list_tool_info()` now includes each tool's
  `capabilities` (read from the matching manifest); `app/api.py`'s
  `ToolInfo` model gained the field to match.
- `app/events.py`: `EventBus` gained a lock around
  subscribe/unsubscribe/emit/clear. `emit()` takes a snapshot of
  listeners under the lock, then calls them outside of it (avoids
  deadlocking a plain `Lock` against a listener that itself
  subscribes/unsubscribes/emits), and now wraps each callback in
  `try/except` so one bad subscriber can't break the rest or propagate
  back into whatever emitted the event.
- `app/container.py`: `ServiceContainer` gained the same lock around
  every method.
- `app/job_manager.py`: `Job` now has its own lock and a `_update()`
  method that applies multiple field changes (e.g.
  `status`+`result`+`progress` together) atomically instead of as
  separate unlocked assignments, plus a `snapshot()` method returning a
  frozen `JobSnapshot` dataclass for a consistent multi-field read.
  `app/api.py`'s `GET /jobs/{id}` now reads via `job.snapshot()` instead
  of separate attribute accesses.
- `app/job_manager.py`: `JobManager` takes `completed_ttl_seconds` and
  `max_completed_jobs` (both default `None`/disabled - a bare
  `JobManager()`, as used throughout the test suite, keeps every job
  forever exactly as before). `submit()` opportunistically prunes
  terminal (completed/failed/cancelled) jobs before adding the new one:
  TTL-expired ones first, then oldest-completed-first if still over the
  count cap. Pending/running jobs are never touched by either
  mechanism. This is lazy pruning, not a background sweep - an expired
  or over-cap job isn't actually removed until the *next* `submit()`
  call, which is an accepted trade for not running a second always-on
  thread just for housekeeping.
- `config/default.yaml` / `app/kernel.py`: added `jobs.completed_ttl_seconds`
  (default `3600`) and `jobs.max_completed_jobs` (default `500`), wired
  through to `JobManager` - real cleanup is on by default for the actual
  app, off by default for the bare class.

Tests added: `tests/test_events.py` and `tests/test_container.py` (both
new files - basic behavior, listener-failure isolation, and a
real-threads concurrency smoke test for each); `tests/test_job_manager.py`
gained `Job.snapshot()`, TTL eviction, max-count eviction
(oldest-first), and a "running job is never evicted regardless of
TTL/count" test; `tests/test_api.py` gained a capabilities-exposure
case. Full suite: 145 passed, the same 1 pre-existing unrelated
failure. Also re-verified with a real `uvicorn` boot: `GET /tools`
capabilities in the response, and a full job create/poll round trip
through the new locking/snapshot/cleanup code path.

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

### Real Bugs Fixed (2026-08-04)
The five "real bugs" from the Full Platform Audit above. Security and
design/scale gaps from that audit remain open - not touched this round.

- `app/config.py`: `Config.get()` now coerces an env var override to
  the type implied by the caller's `default` (bool checked before int,
  since `isinstance(True, int)` is `True`; then int; then float; else
  the raw string is returned unchanged). Verified against a real server
  boot with `JOBS_MAX_WORKERS=8 BROWSER_HEADLESS=false` - previously
  crashed kernel construction, now boots clean.
- `app/kernel.py`: `run_tool()`'s foreground and background paths now
  share one `_run_and_announce()` closure, so `tool.finished` fires for
  both instead of only the synchronous path. Same semantics as before
  otherwise - fires on success only, not on failure/cancellation
  (`job.completed`/`job.failed` already cover those).
- `app/job_manager.py`: `JobManager` now subscribes to `tool.progress`
  on the event bus (same pattern the Kernel already uses for logging)
  and updates the matching `Job.progress` by `job_id`. Foreground
  executions carry a `job_id` never registered in `JobManager._jobs` -
  the handler no-ops safely via `dict.get()` returning `None`.
- `app/api.py`: `run_tool_sync()`'s redundant `except KeyError -> 404`
  around the `kernel.run_tool()` call removed - tool existence is
  already confirmed via `get_manifest()` earlier in the same function,
  so a `KeyError` past that point is the tool's own bug and now
  surfaces as an uncaught exception (a real 500 outside of tests)
  instead of a misleading "Unknown tool".
- `main.py`: corrected the comment above
  `include_router(video_downloader_router)`.

Also corrected while in the area: `CHANGELOG.md`'s "Known limitations"
still claimed `video_downloader` bypasses the Kernel/REST API - false
since Stage 2, removed.

Tests added: `tests/test_config.py` (env var coercion, 6 cases),
`tests/test_kernel.py` (new file - `tool.finished` for both foreground
and background), `tests/test_job_manager.py` (new file - progress
wiring, plus an untracked-`job_id` no-op case), `tests/test_api.py`
(the `KeyError`-misclassification regression). Full suite: 130 passed,
1 pre-existing unrelated failure (see below) - up from 119/1 before
this round. Also re-verified with a real `uvicorn` boot + `curl`
against `main.py`'s actual app, not just unit tests.

### JobManager.shutdown() Bounded Wait (2026-08-05)
Python can't forcibly kill a running thread (unlike the `BrowserManager`
watchdog above, which kills an actual OS process by PID) - so this
isn't a real "stop it now," it's the best available approximation:
signal cooperative cancellation, wait up to a bound, then give up and
let the executor go without joining the stuck thread.

- `app/job_manager.py`: `JobManager.shutdown()` takes an optional
  `timeout`. `timeout=None` (the default) is unchanged - waits
  unboundedly, exactly as before, so every existing no-argument caller
  keeps its current behavior. `timeout=<seconds>` first calls `.cancel()`
  on every still-running job's `CancellationToken` (a real chance for
  any tool that checks `context.raise_if_cancelled()` to stop cleanly
  within the deadline, not just a passive wait), then waits up to
  `timeout` total via `future.result(timeout=...)`. Anything still
  running past the deadline is logged (job IDs named) and left running -
  the executor is released with `wait=False, cancel_futures=True`
  rather than blocking further.
- What this does *not* solve: `ThreadPoolExecutor` registers its own
  `atexit` hook that joins every worker thread at interpreter shutdown,
  regardless of what our `shutdown()` does - so a truly stuck thread can
  still hang final process exit. The real backstop for that is one level
  further out: `docker stop` sends `SIGTERM`, waits a grace period, then
  `SIGKILL`s the whole container - same philosophy as the
  `BrowserManager` watchdog (kill at the OS boundary, don't fight
  Python's threading model), just at the process level instead of the
  browser-process level. Ruled out: forcibly killing the thread via
  `ctypes`/`PyThreadState_SetAsyncExc` (unsafe, doesn't work for threads
  blocked in C extension calls - which is most of what actually hangs),
  and switching to `ProcessPoolExecutor` (would let jobs be OS-killed,
  but `ExecutionContext`/`CancellationToken` hold live locks and thread
  events that don't survive pickling across a process boundary - a real
  architectural change, not a contained fix).
- `config/default.yaml` / `app/kernel.py`: added
  `jobs.shutdown_timeout_seconds` (default `10.0` - float, not int, so
  a fractional env var override coerces correctly), wired through
  `Kernel.shutdown()` so the real app actually uses the bounded path,
  not just an unused optional parameter.

Tests added to `tests/test_job_manager.py`: default (`timeout=None`)
still waits unboundedly; a non-cooperative stuck job is given up on
within the bound and logs a warning naming the job ID; a cooperative
job (checks `raise_if_cancelled()`) actually stops in time because of
the cancellation signal. `tests/test_kernel.py` gained a test proving
the `jobs.shutdown_timeout_seconds` config value is really wired
through `Kernel -> Config -> JobManager.shutdown()`, not just
implemented and left unused - this test caught a real bug in the
process: the config default was `10` (int), and `Config.get()`'s
coercion (see "Real Bugs Fixed") correctly rejected a fractional env
var override against an int default and silently fell back, so the
test's override was being ignored. Fixed by making the default `10.0`
(float) in both `config/default.yaml` and the `kernel.py` call site.
Full suite: 149 passed, the same 1 pre-existing unrelated failure.
Also re-verified with a real `uvicorn` boot + `curl` (normal job
create/poll still works unaffected) and a real `SIGTERM` against the
running process.

### Scheduler Cleanup + REST/CLI Surface (2026-08-05)
Two related fixes: `Scheduler._schedules` had the same unbounded-growth
problem `JobManager._jobs` was fixed for on 2026-08-04, and `Scheduler`
itself was fully built and tested but completely unreachable from
outside the process.

**Cleanup**, mirroring the `JobManager` approach exactly:
- `app/scheduler.py`: `ScheduledJob` gained a `completed_at` field. A
  schedule is terminal for two different reasons that both need
  catching: cancelled before it ever fired (`completed_at` set
  synchronously inside `cancel()`), or fired and the JobManager job it
  dispatched has since finished (`completed_at` set via a new
  `job.completed`/`job.failed`/`job.cancelled` event subscription -
  same pattern `JobManager` already uses for progress - with a
  `job_id -> schedule_id` reverse-lookup so it only reacts to events
  from jobs it actually dispatched, not unrelated `kernel.run_tool()`
  calls). `Scheduler` takes `completed_ttl_seconds` and
  `max_completed_schedules` (both default `None`/disabled, so a bare
  `Scheduler(jobs)` - as used throughout the test suite - keeps every
  schedule forever exactly as before). `schedule()` opportunistically
  prunes before adding the new one, same lazy on-next-call approach as
  `JobManager`.
- `config/default.yaml` / `app/kernel.py`: added `scheduler.
  completed_ttl_seconds` (default `3600`) and `scheduler.
  max_completed_schedules` (default `500`), wired through, plus
  `event_bus=self.events` so the subscription above actually works in
  the real app.

**REST/CLI surface.** The real design question was connecting
"schedule a tool run" to `Scheduler.schedule()`, which takes an
arbitrary `func`, not a tool name - solved with `Kernel.schedule_tool
(delay_seconds, name, **kwargs)`:
- Validates the tool exists and permissions check out *immediately*
  (mirrors `run_tool()`'s own upfront checks) - a bad tool name 404s
  right away instead of silently succeeding and only surfacing as a
  failed job once the timer eventually fires. The same checks run
  again at dispatch time inside `run_tool()` itself too - cheap, and a
  real app could plausibly uninstall a tool or change permissions in
  the gap between scheduling and firing.
- Schedules `self.run_tool` with `background=False` - so the *one*
  JobManager job a schedule dispatches into **is** the actual tool
  execution (full lifecycle, real result), not a throwaway job whose
  result is just another job_id. Known limitation this introduces:
  cancelling an already-*dispatched* schedule only cancels the outer
  JobManager job's `CancellationToken` - `run_tool()`'s synchronous
  (`background=False`) path doesn't check any cancellation token as it
  runs, so it won't actually stop a long-running tool mid-execution
  the way `POST /jobs` + `DELETE /jobs/{id}` can for a cooperative
  tool. Cancelling *before* it fires works cleanly (that path just
  cancels the `Timer`).
- `app/api.py`: `POST /api/v1/schedules` {`delay_seconds`, `tool`,
  `params`} / `GET /api/v1/schedules/{id}` / `DELETE
  /api/v1/schedules/{id}` - deliberately mirroring `/jobs`'s shape
  exactly, including no list endpoint (`/jobs` doesn't have one
  either - the person's explicit choice when asked).
- `cli/client.py` / `cli/main.py`: `multitool schedules create/get/
  cancel`, same structure as the `jobs` subcommand.

Tests: `tests/test_scheduler.py` gained cleanup-disabled-by-default,
TTL eviction (both the cancelled-before-dispatch and
dispatched-and-completed cases), max-count eviction (oldest-first),
and a pending/running-schedules-never-evicted case.
`tests/test_kernel.py` gained `schedule_tool()` tests: unknown-tool and
missing-capability both raise immediately, and a full delay -> real
tool result round trip. `tests/test_api.py` and `tests/test_cli_client.py`
/ `tests/test_cli_main.py` gained the REST and CLI round trips
respectively (create/poll/cancel, unknown-tool 404s, reserved-param
rejection). Full suite: 169 passed, the same 1 pre-existing unrelated
failure. Also re-verified with a real `uvicorn` boot: the full HTTP
create/poll/cancel flow via `curl`, and separately via the actual
installed `multitool` CLI console script against the running server.

### ToolRegistry Per-Execution Instances + PermissionManager Documentation (2026-08-05)
The last two items from the Design/scale gaps list. Closes out that
list entirely except Security (explicitly deferred).

**`ToolRegistry`**: checked the actual blast radius before touching
anything - `get_tool()` has exactly one call site (`kernel.run_tool()`),
every test registers tools via `registry.register(instance)` for setup
only, and neither real tool (`video_downloader`, `video_downloader_
interactive`) overrides `__init__`. Low-risk to fix properly rather
than just document:
- `app/tool_registry.py`: added `create_tool_instance(name)` ->
  `type(self._tools[name])()` - a fresh instance via the same class.
  `get_tool()` is untouched, still returns the one shared instance
  (fine - name/version/description/capabilities are all class-level
  attributes, safe to read off any instance or the class itself).
- `app/kernel.py`: `run_tool()` now calls
  `self.registry.create_tool_instance(name)` instead of `self.get_tool
  (name)` for the instance it actually executes.
- Assumes a no-arg constructor - true for every tool today. A tool
  needing constructor arguments would need a different registration
  path, not just this method; not a problem in practice yet.

**Real fallout, not just theoretical**: this broke 5 existing tests
that turned out to rely on the exact anti-pattern being fixed -
worth recording since it's a genuine, non-obvious discovery, not
swept under the rug:
- Four lifecycle tests (`tests/test_tool_lifecycle.py`) recorded
  `initialize`/`validate`/`run`/`cleanup` calls on `self.calls` /
  `self.cleanup_called`, then asserted against the *externally-held,
  originally-registered* instance - which, after this fix, is no
  longer the instance that actually ran. Fixed by moving that state to
  class-level attributes (shared across every instance of the class
  regardless of which one executed), explicitly reset at the start of
  each test to avoid leaking between tests.
- One workflow retry test (`tests/test_workflow_engine.py`)'s
  `FlakyTool` used `self.calls` to simulate "fails N times then
  succeeds" *across retry attempts* - its own docstring literally said
  "State is per-instance so each test gets a clean counter." Each
  retry is a full fresh `kernel.run_tool()` call, so this only ever
  worked because of the shared-instance bug: real transient failures
  are handled by retrying against changed *external* conditions, not
  by the tool object remembering its own attempt count - a real
  retry-safe tool shouldn't (and now structurally can't) rely on that.
  Fixed the same way: a class-level counter, standing in for a flaky
  external resource instead of tool-internal memory.

**`PermissionManager`**: pushed back on "real enforcement" as the
actual goal here rather than assuming more machinery is automatically
better. `network`/`filesystem` aren't gated by anything in this
architecture - every tool already has unrestricted stdlib access to
both, so a trivial always-true marker service would "enforce" nothing,
just add ceremony around a check that could never fail.
`clipboard`/`database` have no backing service at all yet. `captcha`
does have a real library (`libraries/captcha_manager`), but it's
instantiated directly per-browser-session by tools today, not exposed
as a container service - wiring it up as one is real architecture
work, and part of the CAPTCHA-specific refinement explicitly deferred
elsewhere, not this class's call to make unilaterally. `app/
permission_manager.py` now documents this as an intentional boundary
(with the reasoning above) rather than something that reads like an
unfinished feature.

Tests: `tests/test_tool_registry.py` gained `create_tool_instance()`
tests (fresh instance each call, no state leakage between them,
`get_tool()` still returns the shared instance). `tests/test_kernel.py`
gained an end-to-end regression test with a stateful tool proving
`run_tool()` itself doesn't leak `self` state across two sequential
calls. Full suite: 173 passed, the same 1 pre-existing unrelated
failure - after fixing the 5 tests above that this change legitimately
broke. Also re-verified with a real `uvicorn` boot: tool listing,
and a job create/poll round trip run sequentially twice to confirm the
general request/response plumbing is unaffected.

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
- ~~`Config.get()` env-var overrides aren't type-coerced~~ - fixed
  2026-08-04, see "Real Bugs Fixed" above.
- ~~`tool.finished` never fires for background jobs~~ - fixed
  2026-08-04, see "Real Bugs Fixed" above.
- ~~`context.report_progress()` disconnected from `job.progress`~~ -
  fixed 2026-08-04, see "Real Bugs Fixed" above.
- ~~`POST /tools/{name}/run`'s `KeyError` handling can misclassify a
  tool's own internal bug as "Unknown tool"~~ - fixed 2026-08-04, see
  "Real Bugs Fixed" above.
- ~~`main.py`'s stale comment about video_downloader_router still
  bypassing the kernel~~ - fixed 2026-08-04, see "Real Bugs Fixed" above.
- No authentication on the REST API; CORS wide open - see "Full
  Platform Audit" / Current Focus.
- ~~`ToolRegistry` shared tool instances are a footgun for future tool
  authors~~ - fixed 2026-08-05, see "ToolRegistry Per-Execution
  Instances + PermissionManager Documentation" above.
- ~~`PermissionManager` only enforces `browser`~~ - documented
  2026-08-05 as an intentional boundary rather than fixed as "real
  enforcement" - see "ToolRegistry Per-Execution Instances +
  PermissionManager Documentation" above for why.
- ~~`Scheduler` has no REST/CLI surface~~ - fixed 2026-08-05, see
  "Scheduler Cleanup + REST/CLI Surface" above.
- ~~`JobManager.shutdown()` can block indefinitely on a stuck job~~ -
  fixed 2026-08-05, see "JobManager.shutdown() Bounded Wait" above.
- ~~`JobManager._jobs` never cleaned up~~ - fixed 2026-08-04 for
  `JobManager` (TTL + max-count eviction). `Scheduler._schedules` had
  the same issue - fixed 2026-08-05, see "Scheduler Cleanup + REST/CLI
  Surface" above.
- ~~`GET /api/v1/tools` doesn't expose capabilities~~ - fixed
  2026-08-04, see "Design/Scale Gaps Fixed" above.
- ~~`EventBus`/`ServiceContainer` have no locking or listener
  isolation~~ - fixed 2026-08-04, see "Design/Scale Gaps Fixed" above.
- ~~Make Job updates thread-safe~~ - fixed 2026-08-04: `Job` now has its
  own lock and an atomic `_update()` used for every compound field
  change. See "Design/Scale Gaps Fixed" above.
- ~~Add immutable job snapshots~~ - fixed 2026-08-04: `Job.snapshot()`
  returns a frozen `JobSnapshot`; `GET /jobs/{id}` uses it. See
  "Design/Scale Gaps Fixed" above.
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


