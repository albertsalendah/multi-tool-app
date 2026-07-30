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
