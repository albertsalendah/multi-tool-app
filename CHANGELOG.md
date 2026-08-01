# Changelog

All notable changes to this project will be documented in this file.

The format follows Keep a Changelog principles and Semantic Versioning where applicable.

## [0.2.0-platform] - 2026-07-30

### Added
- Application Kernel, Service Container, Configuration System, Logging System.
- Tool Registry with Plugin Discovery, driven by per-tool `manifest.json`.
  A single broken plugin is now logged and skipped instead of crashing
  discovery for every other tool.
- Job Manager (background execution, cancellation) and Browser Manager
  (Playwright-based).
- Event Bus, with default logging subscriptions for `tool.*` and
  `workflow.*` events.
- Capability & Permission System, and Execution Context (per-execution
  request/state/services, cooperative cancellation).
- Scheduler for one-time delayed job dispatch.
- Workflow Engine: linear steps with variable substitution, retry,
  per-step timeout, conditions, and `continue_on_error`; `ParallelGroup`
  execution (branches run concurrently, every branch runs to completion
  before failures are raised together); `workflow.started` /
  `.progress` / `.completed` / `.failed` events.
- Plugin SDK: `BaseTool` now has a real per-execution
  `initialize() -> validate() -> run() -> cleanup()` lifecycle instead
  of just `run()`.
- REST API (`/api/v1`): `GET /health`, `GET /tools`, `POST /jobs`,
  `GET /jobs/{id}`, `DELETE /jobs/{id}` - the Kernel is now reachable
  over HTTP, not just in-process.
- CLI: installable `multitool` console script (`pip install -e .`),
  a REST API client covering health, tool listing, and the full job
  lifecycle (create/get/cancel, with optional polling via `--wait`).
- Web UI (fast path): `POST /api/v1/tools/{name}/run` added for
  synchronous tool execution. `video_downloader`'s info-lookup now
  goes through the Kernel/Plugin SDK lifecycle instead of a bespoke
  endpoint that bypassed it entirely; its manifest capabilities were
  narrowed to match what it actually does. Also fixed an unrelated bug
  found in the process: `GET /tools/video-downloader` (the page
  itself) was 500ing on every request due to a wrong static-file path.
- Browser stack decided: SeleniumBase, replacing Playwright entirely.
  `Browser Manager` rewritten to `acquire()`/`release()`/`shutdown()`
  session semantics (SeleniumBase has no shared-process model to
  initialize up front, unlike Playwright). Removed from
  `requirements.txt`; `Dockerfile`'s browser install step now installs
  real Google Chrome + a matching chromedriver instead.
- Web UI (interactive/CAPTCHA path): new `video_downloader_interactive`
  tool replaces `selenium_detector.py`'s broken pipeline (opened a
  browser, checked for CAPTCHA, then never returned a result - hung
  forever) with one that actually completes and goes through
  `kernel.run_tool()`/the Job Manager. `stream_extractor.py`'s stale
  pre-migration import fixed. `static/app.js`'s "Try generic
  detection" now uses `POST /api/v1/jobs` + polling, same as any other
  job, instead of a bespoke session-tracking endpoint.
- Test suite covering all of the above (`tests/`).

### Known limitations
- `video_downloader` (the one real tool so far) still bypasses the
  Kernel/REST API entirely via its own bespoke router - reconciling
  that is intentionally deferred until more tools exist.
- No streaming/live-progress endpoint yet; job status is poll-only.

## [0.1.0-architecture] - 2026-07-29

### Added
- Defined project vision as a Modular Automation Processing Platform.
- Established architecture freeze process.
- Introduced platform-first philosophy.
- Defined core platform services.
- Adopted job-based execution model.
- Adopted plugin-oriented tool architecture.
- Established temporary processing and cloud delivery philosophy.

### Planned
- Complete Architecture Design Document.
- Refactor project structure.
- Implement Application Kernel.
- Implement Tool Registry and Plugin Discovery.
- Introduce Browser Manager and Job Manager.
- Integrate CAPTCHA framework as a shared library.
