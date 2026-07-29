# ADR-0001: Platform Philosophy

Status: Accepted

## Context
The project is evolving from a single-purpose application into a reusable automation platform.

## Decision
Adopt a platform-first architecture where:
- The Platform orchestrates.
- Tools implement business logic.
- Platform Services provide shared infrastructure.
- Shared Libraries provide reusable capabilities.

## Consequences
- New features should be implemented as Tools.
- Shared functionality belongs in Services or Libraries.
- Reduced duplication and improved maintainability.
