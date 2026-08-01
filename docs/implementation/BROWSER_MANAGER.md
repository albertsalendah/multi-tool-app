# Browser Manager

## Purpose
Provide browser instances to jobs.

## Implementation
SeleniumBase-based (`app/browser_manager.py`) - see
`docs/ARCHITECTURE_CHANGELOG.md`'s browser-stack decision. Each
`acquire()` starts a genuinely new session; SeleniumBase's `SB()` is a
per-session context manager, not a shared browser process you can
cheaply spin sub-contexts from.

## Responsibilities
- Session lifecycle (implemented)
- Release resources (implemented)
- Browser pool - **not yet implemented**, still a separate roadmap
  item. Every `acquire()` today launches a fresh session; nothing is
  reused.
- Health checks - not yet implemented

## Exposes
acquire(), release(), shutdown()
