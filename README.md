# Multi Tool App

> **A Modular Automation Processing Platform**

## Vision
Multi Tool App is an extensible platform for browser-powered and non-browser-powered automation tools. The platform provides reusable infrastructure so each tool can focus on its own business logic.

## Core Principles
- Platform First
- Job-Based Execution
- Plugin-Oriented Architecture
- Provider Agnostic
- Temporary Processing
- Event-Driven Design
- Secure by Default

## Planned Platform Services
- Application Kernel
- Tool Registry & Plugin Discovery
- Job Manager
- Browser Manager
- CAPTCHA Manager (Shared Library)
- Output Manager
- Storage Manager
- Credential Vault
- Authentication
- Event Bus
- Resource Manager

## Tool Philosophy
Every feature is implemented as a Tool. The platform owns orchestration while tools perform work.

## Storage Philosophy
Processed files are temporary. Users may:
1. Download directly.
2. Upload to a linked cloud storage provider.
3. Have temporary files automatically cleaned up.

## Documentation
This repository contains architecture documentation under `docs/` (to be added during the architecture freeze).

## Roadmap
Completed: Architecture Freeze, Platform Refactor, Core Services
(Kernel, Registry, Job Manager, Browser Manager, Event Bus, Execution
Context, Scheduler), Workflow Engine, Plugin SDK, REST API, CLI, the
web UI's fast-path reconciliation with the REST API, and the browser
stack decision (SeleniumBase).
Current focus: the interactive/CAPTCHA path (Stage 2 of the web UI
reconciliation), now unblocked. See `docs/STATUS.md` for the full
checklist and `docs/ARCHITECTURE_CHANGELOG.md` for details.

## License
TBD
