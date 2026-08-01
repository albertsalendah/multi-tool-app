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

## Current Milestone
Finish Stage 2 of the web UI reconciliation (interactive/CAPTCHA path)
now that the browser stack is decided:
- Fix `selenium_detector.py`'s session pipeline (never resolves today)
- Fix `stream_extractor.py`'s stale pre-migration import
- Rebuild the interactive detection flow as a real `BaseTool` going
  through `kernel.run_tool()` / the Job Manager, replacing its own
  ad-hoc `SESSIONS` dict
- Rewire `static/app.js`'s "Try generic detection" button to
  `/api/v1/jobs` + polling, replacing the bespoke
  `detect-interactive`/`session/{id}/status` routes

## Next Milestones
- Interactive/CAPTCHA path reconciliation (Stage 2, in progress - see
  Current Milestone)
- Real Tools (beyond video_downloader)
- Desktop UI / Mobile app - deferred until the web app is solid
