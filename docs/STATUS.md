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
- [x] REST API (/api/v1: health, tools, jobs)
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

## Current Milestone
None actively in progress. The "Real bugs" bucket of the platform
audit is now clear. Remaining from Known Technical Debt in
`docs/ARCHITECTURE_CHANGELOG.md`: the Security and Design/scale-gap
findings (all still open), plus two undecided items, in the person's
own stated priority:
1. General tool-execution timeout design (separate from the
   BrowserManager watchdog above, which only covers browser hangs)
2. No authentication on the REST API at all - low risk while
   local-only, real risk the moment this is exposed beyond one machine

## Next Milestones
- video_downloader/CAPTCHA-specific improvements (explicitly deferred
  by the person until "everything else" is handled first - e.g. the
  120s-flat CAPTCHA manual-wait, wiring the new BrowserManager timeout
  into the interactive tool)
- Real Tools (beyond video_downloader)
- Browser Pool (reuse acquired sessions instead of one per acquire())
- Desktop UI / Mobile app - deferred until the web app is solid
