from __future__ import annotations

from threading import Lock
from typing import Any, Callable, Optional


class BrowserManager:
    """
    Provides SeleniumBase browser sessions to jobs.

    SeleniumBase's SB() is a per-session context manager, not a shared
    browser process you can cheaply open sub-contexts from (unlike
    Playwright's Browser/BrowserContext model, which this replaced -
    see docs/ARCHITECTURE_CHANGELOG.md's browser-stack decision). So
    each acquire() starts a genuinely new session; there's no pooling
    yet - that's the separate "Browser Pool" roadmap item.

    driver_factory defaults to the real seleniumbase.SB and is only a
    constructor parameter so tests can inject a fake one instead of
    needing a real browser installed.
    """

    def __init__(
        self,
        default_headless: bool = True,
        driver_factory: Optional[Callable[..., Any]] = None,
    ):
        self._default_headless = default_headless
        self._driver_factory = driver_factory
        self._sessions: dict[int, Any] = {}
        self._lock = Lock()

    def _factory(self) -> Callable[..., Any]:
        if self._driver_factory is not None:
            return self._driver_factory

        from seleniumbase import SB

        return SB

    def acquire(self, **overrides) -> Any:
        """Start a new SeleniumBase session and return the driver (sb).
        Keyword arguments are passed through to SB(...), e.g.
        headless=False for flows that need a visible browser (manual
        CAPTCHA solving). Falls back to the configured default_headless
        when not overridden."""

        options = {"headless": self._default_headless}
        options.update(overrides)

        context_manager = self._factory()(**options)
        sb = context_manager.__enter__()

        with self._lock:
            self._sessions[id(sb)] = context_manager

        return sb

    def release(self, sb: Any) -> None:
        """Tear down a session previously returned by acquire(). Safe to
        call on a session that's already been released (or was never
        tracked) - it's just a no-op."""

        with self._lock:
            context_manager = self._sessions.pop(id(sb), None)

        if context_manager is not None:
            context_manager.__exit__(None, None, None)

    def shutdown(self) -> None:
        """Release any sessions a caller forgot to release - a safety
        net for kernel shutdown, not the normal path (tools should
        release() in their own cleanup())."""

        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()

        for context_manager in sessions:
            try:
                context_manager.__exit__(None, None, None)
            except Exception:
                pass
