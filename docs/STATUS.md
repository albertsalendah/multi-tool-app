# Multi Tool App Status

## Completed
- [x] Project restructuring
- [x] Application Kernel
- [x] Tool Registry
- [x] Plugin Discovery
- [x] Job Manager
- [x] Browser Manager
- [x] Event Bus
- [x] Configuration System
- [x] Logging System
- [x] Service Container
- [x] Plugin Manifest & Metadata System
- [x] Capability & Permission System
- [x] Shared Context / Execution Context
- [x] Cancellation Token
- [x] Scheduler
- [x] Workflow Engine (linear steps, ParallelGroup, retry/timeout/condition/continue_on_error)
- [x] Workflow Events (workflow.started/progress/completed/failed)
- [x] Plugin SDK (real initialize/validate/run/cleanup lifecycle, resilient discovery)
- [x] REST API (/api/v1: health, tools, jobs, schedules)
- [x] CLI (installable `multitool` console script, REST API client -
      pip install -e .)
- [x] Web UI fast-path reconciliation - GET /tools/video-downloader/info
      replaced by POST /api/v1/tools/video_downloader/run, going
      through the Kernel/Plugin SDK lifecycle instead of bypassing it
- [x] Browser stack decision: SeleniumBase (not Playwright). Browser
      Manager rewritten to acquire()/release()/shutdown() sessions;
      Playwright removed from requirements.txt/Dockerfile entirely.
- [x] Web UI Stage 2 - interactive/CAPTCHA path reconciled. New
      `video_downloader_interactive` tool (separate from
      `video_downloader` since it needs the `browser` capability and
      the fast tool doesn't) replaces the broken `selenium_detector.py`
      pipeline (which never returned a result) and goes through
      `kernel.run_tool()`/the Job Manager instead of its own ad-hoc
      `SESSIONS` dict. `stream_extractor.py`'s stale pre-migration
      import fixed. `static/app.js`'s "Try generic detection" now uses
      `POST /api/v1/jobs` + polling.
- [x] Full platform audit (everything outside video_downloader/CAPTCHA
      specifics, which are intentionally deferred) - see
      `docs/ARCHITECTURE_CHANGELOG.md`'s Known Technical Debt for the
      complete findings list, most still open. Six items already fixed
      this round (see below).
- [x] `BrowserManager` PID-tracking + watchdog: `acquire(timeout=...)`
      starts a watchdog that force-kills (SIGKILL, via the real PID -
      `driver.browser_pid` for `uc=True` sessions, else
      `driver.service.process.pid`) a session's OS-level browser
      process if it isn't `release()`'d in time. Answers the "stuck
      browser hang" case concretely - verified against real
      self-controlled subprocesses, not mocked. Deliberately scoped to
      `BrowserManager` only; NOT yet wired into any tool's
      `initialize()` call (that's part of the video_downloader-specific
      follow-up, still deferred) and does NOT answer the broader "should
      tool executions get a wrapping timeout" design question (still open).
- [x] Six minor fixes from the platform audit: `.gitignore` now covers
      `logs/*.log`; `Config` warns and falls back to defaults instead of
      silently continuing (missing file) or crashing (malformed YAML);
      `CONFIGURATION_SCHEMA.md`/`ERROR_CODES.md` doc drift corrected
      (marked aspirational sections/codes as not-yet-implemented rather
      than implying they're live); unused `import inspect` removed from
      `app/tool_registry.py`; `POST /api/v1/jobs` and
      `POST /api/v1/tools/{name}/run` now reject a `params` dict that
      collides with `run_tool()`'s own `name`/`background` arguments
      (was an unhandled 500, now a clean 400).

- [x] Audit "Real bugs" fixed (2026-08-04): env var type-coercion in
      `Config.get()`; `tool.finished` now fires for background jobs;
      `context.report_progress()` wired through to `Job.progress`;
      `POST /tools/{name}/run` no longer misreports a tool's own
      internal `KeyError` as `404 Unknown tool`; `main.py`'s stale
      router comment corrected. See `docs/ARCHITECTURE_CHANGELOG.md`'s
      "Real Bugs Fixed" for detail.
- [x] Audit "Design/scale gaps" partially fixed (2026-08-04, the
      "straightforward" subset plus JobManager cleanup - explicitly
      chosen over the ones needing a design call first): `GET
      /api/v1/tools` now exposes `capabilities`; `EventBus`/
      `ServiceContainer` gained locking + listener-failure isolation;
      `Job` gained its own lock, an atomic `_update()`, and a
      `snapshot()` used by `GET /jobs/{id}`; `JobManager` now
      TTL/max-count-evicts completed jobs (config-driven, disabled by
      default for the bare class).
- [x] `JobManager.shutdown()` bounded wait (2026-08-05): takes an
      optional `timeout` - signals cooperative cancellation on
      still-running jobs first, waits up to the bound, then gives up
      and logs rather than blocking forever. Default (no argument)
      unchanged - still waits unboundedly. Wired through
      `Kernel.shutdown()` via `jobs.shutdown_timeout_seconds` (default
      10s) so the real app actually uses it. Does not solve interpreter-
      exit-time hangs from `ThreadPoolExecutor`'s own `atexit` hook -
      that's a container-level (`docker stop`) problem, not a
      Python-level one. See `docs/ARCHITECTURE_CHANGELOG.md`'s
      "JobManager.shutdown() Bounded Wait" for detail, including why a
      real thread-kill or `ProcessPoolExecutor` switch were ruled out.
- [x] Scheduler cleanup + REST/CLI surface (2026-08-05):
      `Scheduler._schedules` now TTL/max-count-evicts terminal
      schedules the same way `JobManager` does (event-driven -
      subscribes to `job.completed`/`failed`/`cancelled` to detect a
      dispatched schedule's underlying job finishing). New
      `Kernel.schedule_tool()` connects scheduling to actual tool
      execution with upfront validation (bad tool name / missing
      capability fails immediately, not once the timer fires). New
      `POST /schedules`, `GET /schedules/{id}`, `DELETE
      /schedules/{id}` (mirrors `/jobs`, no list endpoint - the
      person's explicit choice) plus matching `multitool schedules
      create/get/cancel` CLI commands. Known limitation: cancelling an
      already-dispatched schedule can't cooperatively stop the tool
      mid-run (only pre-dispatch cancellation is clean) - see
      `docs/ARCHITECTURE_CHANGELOG.md`'s "Scheduler Cleanup + REST/CLI
      Surface" for why.
- [x] ToolRegistry per-execution instances + PermissionManager
      documentation (2026-08-05) - the final two Design/scale gaps,
      closing that list out entirely (Security aside, which stays
      explicitly deferred). `ToolRegistry.create_tool_instance()`
      gives `run_tool()` a fresh tool instance every execution instead
      of one shared instance forever - closes the state-leak footgun
      structurally rather than just by convention. This broke 5
      existing tests that turned out to be relying on the exact
      anti-pattern being fixed (worth knowing about, not just fixed
      quietly - see `docs/ARCHITECTURE_CHANGELOG.md`). `PermissionManager`
      now documents why only `browser` is really enforced instead of
      reading like an unfinished feature - a deliberate call, not
      "real enforcement machinery" for capabilities with nothing
      concrete to check against yet.

## Current Milestone
None actively in progress on the platform side. The Design/scale gaps
list from the full platform audit is now fully closed out. Remaining
from Known Technical Debt in `docs/ARCHITECTURE_CHANGELOG.md`:
Security (explicitly deferred by the person while testing locally),
and the general tool-execution timeout question - discussed at length
and explicitly decided to wait on for now (reasoning: the only real
mechanism is cooperative-cancellation-plus-give-up, same limitation
`JobManager.shutdown()` has, and only one tool checks cancellation at
all today, at two coarse points - building general timeout
infrastructure around tools whose own shape isn't settled yet was
judged premature). Revisit either once explicitly prioritized.

The actual current focus is CAPTCHA/`video_downloader` design work -
see `docs/HANDOVER_2026-08-21.md` for the full, detailed state of
this; summary immediately below.

## Next Milestones
- **CAPTCHA/`video_downloader` architecture - in progress, not just
  deferred anymore.** Two spike tracks:
  - Domain-lock spike (`docs/spikes/captcha-domain-lock-spike.html`):
    one real finding confirmed (reCAPTCHA v2 is genuinely domain-locked
    against a real site's key), hCaptcha still needing a clean re-test,
    Turnstile not yet started.
  - **Screencast/click-forwarding spike
    (`docs/spikes/captcha_screencast_test.py`) - now confirmed working
    end to end, not just viewing.** Real reCAPTCHA image-selection
    challenges solved successfully from desktop Firefox, desktop
    Chrome, Android Chrome, and 1DM+, across two physical machines plus
    a phone over LAN. MJPEG push transport confirmed broken in Chrome/
    Chromium specifically (works in Firefox only); replaced with plain
    polling, which works everywhere. `headless=True` also retested
    clean under the polling architecture, overturning an earlier
    (unverified) claim that headless screencast produces blank frames -
    real implication: a human may no longer need to see the actual
    browser window to solve a CAPTCHA, which is what the current
    `headless=False` requirement in `tool.py` exists for.
  - **Open design question still unresolved**: the captured frame is
    the whole page, so the CAPTCHA renders tiny unless the browser
    window is shrunk - fine for a spike, not viable in production
    against arbitrary third-party sites (risks tripping a site's
    mobile/responsive layout). Real answer is likely cropping to the
    CAPTCHA element's actual on-page bounding box via
    `libraries/captcha_manager`'s existing detector/selectors - not
    built yet.
  - Full detail, findings, and suggested next steps in
    `docs/HANDOVER_2026-08-21.md`.
- Real Tools (beyond video_downloader)
- Browser Pool (reuse acquired sessions instead of one per acquire())
- Desktop UI / Mobile app - deferred until the web app is solid
