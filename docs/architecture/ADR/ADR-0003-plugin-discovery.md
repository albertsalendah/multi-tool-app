# ADR-0003: Plugin Discovery

Status: Accepted

## Context
The platform should grow without modifying the core for every new feature.

## Decision
Implement a Tool Registry with Plugin Discovery.

Responsibilities:
- Discover installed tools
- Validate tool metadata
- Register capabilities
- Expose tools to the platform

## Consequences
- Extensible architecture
- Simplified tool development
- Stable platform core
