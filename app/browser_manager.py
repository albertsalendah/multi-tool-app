from __future__ import annotations

import os
import signal
from dataclasses import dataclass
from threading import Lock, Timer
from typing import Any, Callable, Optional


def _resolve_pid(sb: Any) -> Optional[int]:
    """Best-effort resolution of the OS process PID for the browser a
    session controls. Different seleniumbase modes expose it
    differently - confirmed against the real installed library, not
    guessed:

    - undetected-chromedriver mode (uc=True, what this app's
      CAPTCHA-solving flow uses) sets driver.browser_pid directly.
      SeleniumBase's own internal cleanup uses this exact attribute
      the same way (os.kill(self.browser_pid, 15) in
      seleniumbase/undetected/__init__.py), so this is a real,
      supported mechanism, not a private implementation detail we're
      reaching past.
    - Plain (non-uc) sessions only have the chromedriver subprocess
      PID, via the standard Selenium API: driver.service.process.pid.

    Returns None if neither is available (e.g. a fake driver in tests,
    or a session that failed to fully start).
    """
    driver = getattr(sb, "driver", None)
    if driver is None:
        return None

    browser_pid = getattr(driver, "browser_pid", None)
    if browser_pid:
        return browser_pid

    service = getattr(driver, "service", None)
    process = getattr(service, "process", None)
    pid = getattr(process, "pid", None)
    if pid:
        return pid

    return None


@dataclass(slots=True)
class _TrackedSession:
    sb: Any
    context_manager: Any
    watchdog: Optional[Timer] = None


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

    Optional watchdog: pass timeout= to acquire() to have the session's
    OS-level browser process force-killed (SIGKILL, via the real PID -
    see _resolve_pid) if it isn't release()'d within that many seconds.
    This exists because Python threads can't be forcibly stopped from
    outside - if a tool's run() hangs on a stuck browser launch, the
    JobManager worker thread running it is gone until the underlying
    blocking call returns, which might be never. Killing the actual OS
    process out from under it typically makes that call fail promptly
    instead. This is scoped to BrowserManager only, independent of any
    job- or workflow-level timeout - it's not a general "tool execution
    timeout" (that's a separate, still-open question - see
    docs/ARCHITECTURE_CHANGELOG.md).
    """

    def __init__(
        self,
        default_headless: bool = True,
        driver_factory: Optional[Callable[..., Any]] = None,
    ):
        self._default_headless = default_headless
        self._driver_factory = driver_factory
        self._sessions: dict[int, _TrackedSession] = {}
        self._lock = Lock()

    def _factory(self) -> Callable[..., Any]:
        if self._driver_factory is not None:
            return self._driver_factory

        from seleniumbase import SB

        return SB

    def acquire(self, timeout: Optional[float] = None, **overrides) -> Any:
        """Start a new SeleniumBase session and return the driver (sb).

        Keyword arguments are passed through to SB(...), e.g.
        headless=False for flows that need a visible browser (manual
        CAPTCHA solving). Falls back to the configured default_headless
        when not overridden.

        timeout: if given, a watchdog starts immediately. If the
        session isn't release()'d within `timeout` seconds, its
        underlying OS browser process is force-killed and the session
        is torn down automatically. None (default) disables this -
        matches today's behavior exactly.
        """

        options = {"headless": self._default_headless}
        options.update(overrides)

        context_manager = self._factory()(**options)
        sb = context_manager.__enter__()

        session_id = id(sb)
        watchdog: Optional[Timer] = None

        if timeout is not None:
            watchdog = Timer(timeout, self._on_watchdog_timeout, args=(session_id,))
            watchdog.daemon = True

        with self._lock:
            self._sessions[session_id] = _TrackedSession(
                sb=sb, context_manager=context_manager, watchdog=watchdog
            )

        if watchdog is not None:
            watchdog.start()

        return sb

    def _on_watchdog_timeout(self, session_id: int) -> None:
        """Runs on the Timer's own thread. If the session is still
        outstanding, force-kill its OS process and drop it from
        tracking. If it was already release()'d normally (the race is
        resolved by whoever pops it from _sessions first), this is a
        no-op - release() already cancels the timer, but a timer that
        was already in-flight when release() ran could still reach
        here and find nothing left to do."""

        with self._lock:
            session = self._sessions.pop(session_id, None)

        if session is None:
            return

        pid = _resolve_pid(session.sb)

        if pid is not None:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # already gone
            except Exception:
                pass  # best-effort; a watchdog thread must never crash

        try:
            session.context_manager.__exit__(None, None, None)
        except Exception:
            # The process is likely already dead at this point, so
            # SeleniumBase's own teardown may fail trying to talk to
            # it. Best-effort cleanup only - the PID kill above is what
            # actually mattered.
            pass

    def release(self, sb: Any) -> None:
        """Tear down a session previously returned by acquire(). Safe to
        call on a session that's already been released (or was never
        tracked) - it's just a no-op. Cancels any outstanding watchdog
        for this session."""

        with self._lock:
            session = self._sessions.pop(id(sb), None)

        if session is None:
            return

        if session.watchdog is not None:
            session.watchdog.cancel()

        session.context_manager.__exit__(None, None, None)

    def shutdown(self) -> None:
        """Release any sessions a caller forgot to release - a safety
        net for kernel shutdown, not the normal path (tools should
        release() in their own cleanup()). Cancels outstanding
        watchdogs first so they don't fire concurrently with this
        sweep (harmless either way - the dict-pop makes both paths
        safe - but tidier)."""

        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()

        for session in sessions:
            if session.watchdog is not None:
                session.watchdog.cancel()

            try:
                session.context_manager.__exit__(None, None, None)
            except Exception:
                pass
