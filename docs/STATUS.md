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

## Current Milestone
Undecided - open question raised while finishing Stage 2: should tool
executions get a wrapping timeout (like `WorkflowStep` already has),
so a stuck browser launch or other slow operation can't tie up a
`JobManager` worker thread indefinitely? Not implemented yet - flagged
for discussion, not decided unilaterally.

## Next Milestones
- Real Tools (beyond video_downloader)
- Browser Pool (reuse acquired sessions instead of one per acquire())
- Desktop UI / Mobile app - deferred until the web app is solid
