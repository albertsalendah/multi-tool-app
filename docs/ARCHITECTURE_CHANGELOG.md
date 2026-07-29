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

### Current Focus
Implement Workflow Engine

### Known Technical Debt
- Fix JobManager submit race condition.
- Make Job updates thread-safe.
- Add cooperative cancellation token.
- Add immutable job snapshots.
