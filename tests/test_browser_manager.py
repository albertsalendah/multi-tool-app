import subprocess
import time
import types

from app.browser_manager import BrowserManager


class FakeDriver:
    def __init__(self, browser_pid=None):
        self.browser_pid = browser_pid


class FakeSession:
    """Mimics what SB(...) actually returns: a context manager whose
    __enter__ yields the driver (here, itself) and whose __exit__ tears
    it down. Tracks calls so tests can assert on them.

    browser_pid is a test-only convenience for the watchdog tests (a
    real SB() session wouldn't take this as a constructor kwarg - the
    PID gets discovered from the real driver after acquisition, not
    passed in). Any other kwarg flows into .options like before."""

    def __init__(self, browser_pid=None, **options):
        self.options = options
        self.entered = False
        self.exit_count = 0
        self.raise_on_exit = False
        self.driver = FakeDriver(browser_pid) if browser_pid is not None else None

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *exc_info):
        self.exit_count += 1
        if self.raise_on_exit:
            raise RuntimeError("simulated teardown failure")
        return False


def fake_factory(**options):
    return FakeSession(**options)


def test_acquire_returns_the_entered_driver():
    manager = BrowserManager(driver_factory=fake_factory)

    sb = manager.acquire()

    assert isinstance(sb, FakeSession)
    assert sb.entered is True


def test_acquire_applies_default_headless_when_not_overridden():
    manager = BrowserManager(default_headless=True, driver_factory=fake_factory)

    sb = manager.acquire()

    assert sb.options["headless"] is True


def test_acquire_override_beats_the_default():
    manager = BrowserManager(default_headless=True, driver_factory=fake_factory)

    # Manual CAPTCHA-solving flows need a visible browser regardless of
    # the configured default - this is the override path for that.
    sb = manager.acquire(headless=False)

    assert sb.options["headless"] is False


def test_acquire_passes_through_arbitrary_options():
    manager = BrowserManager(driver_factory=fake_factory)

    sb = manager.acquire(uc=True, ad_block=True)

    assert sb.options["uc"] is True
    assert sb.options["ad_block"] is True


def test_release_tears_down_the_session():
    manager = BrowserManager(driver_factory=fake_factory)
    sb = manager.acquire()

    manager.release(sb)

    assert sb.exit_count == 1


def test_release_is_a_noop_for_an_untracked_session():
    manager = BrowserManager(driver_factory=fake_factory)
    never_acquired = FakeSession()

    manager.release(never_acquired)  # should not raise

    assert never_acquired.exit_count == 0


def test_releasing_twice_only_tears_down_once():
    manager = BrowserManager(driver_factory=fake_factory)
    sb = manager.acquire()

    manager.release(sb)
    manager.release(sb)

    assert sb.exit_count == 1


def test_shutdown_releases_all_outstanding_sessions():
    manager = BrowserManager(driver_factory=fake_factory)
    first = manager.acquire()
    second = manager.acquire()

    manager.shutdown()

    assert first.exit_count == 1
    assert second.exit_count == 1


def test_shutdown_is_safe_with_no_outstanding_sessions():
    manager = BrowserManager(driver_factory=fake_factory)

    manager.shutdown()  # should not raise


def test_shutdown_continues_past_a_session_that_fails_to_tear_down():
    manager = BrowserManager(driver_factory=fake_factory)
    broken = manager.acquire()
    broken.raise_on_exit = True
    healthy = manager.acquire()

    manager.shutdown()  # should not raise despite `broken` erroring

    assert broken.exit_count == 1
    assert healthy.exit_count == 1


def test_already_released_session_is_dropped_from_shutdown():
    manager = BrowserManager(driver_factory=fake_factory)
    sb = manager.acquire()
    manager.release(sb)

    manager.shutdown()

    # Only the one release() call should have torn it down.
    assert sb.exit_count == 1


def test_default_driver_factory_resolves_to_the_real_seleniumbase_sb():
    """Without an injected factory, BrowserManager should wire up to
    the real seleniumbase.SB - checked by import identity only, since
    actually calling it needs a real browser this test environment
    doesn't have."""
    from seleniumbase import SB

    manager = BrowserManager()

    assert manager._factory() is SB


# --------------------------------------------------------------------------
# _resolve_pid: confirmed against the real installed seleniumbase/selenium
# libraries (see app/browser_manager.py's docstring) - these tests check
# the resolution logic/priority, not the real library itself.
# --------------------------------------------------------------------------


def test_resolve_pid_prefers_browser_pid_over_service_process_pid():
    from app.browser_manager import _resolve_pid

    process = types.SimpleNamespace(pid=999)
    service = types.SimpleNamespace(process=process)
    driver = types.SimpleNamespace(browser_pid=111, service=service)
    sb = types.SimpleNamespace(driver=driver)

    assert _resolve_pid(sb) == 111


def test_resolve_pid_falls_back_to_service_process_pid():
    from app.browser_manager import _resolve_pid

    process = types.SimpleNamespace(pid=999)
    service = types.SimpleNamespace(process=process)
    driver = types.SimpleNamespace(service=service)  # no browser_pid
    sb = types.SimpleNamespace(driver=driver)

    assert _resolve_pid(sb) == 999


def test_resolve_pid_returns_none_when_nothing_is_available():
    from app.browser_manager import _resolve_pid

    assert _resolve_pid(types.SimpleNamespace(driver=types.SimpleNamespace())) is None
    assert _resolve_pid(types.SimpleNamespace()) is None  # no .driver at all


# --------------------------------------------------------------------------
# Watchdog: real (safely self-controlled) subprocesses, so these prove the
# actual SIGKILL mechanism works end to end, not just that a mock fired.
# --------------------------------------------------------------------------


def _spawn_sleeper() -> subprocess.Popen:
    return subprocess.Popen(
        ["sleep", "100"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def _cleanup(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.kill()
    proc.wait(timeout=5)


def test_watchdog_kills_the_real_process_after_timeout():
    proc = _spawn_sleeper()
    try:
        manager = BrowserManager(driver_factory=fake_factory)
        manager.acquire(browser_pid=proc.pid, timeout=0.2)

        assert proc.poll() is None  # still alive right after acquire

        time.sleep(0.8)  # let the watchdog fire

        assert proc.poll() is not None  # now dead
    finally:
        _cleanup(proc)


def test_watchdog_does_not_fire_if_released_before_timeout():
    proc = _spawn_sleeper()
    try:
        manager = BrowserManager(driver_factory=fake_factory)
        sb = manager.acquire(browser_pid=proc.pid, timeout=1.0)

        manager.release(sb)

        time.sleep(1.3)  # past when the watchdog would have fired

        assert proc.poll() is None  # never killed - released in time
    finally:
        _cleanup(proc)


def test_watchdog_kills_the_process_even_if_shutdown_never_runs_first():
    """The watchdog fires on its own timer regardless of whether
    shutdown() is ever called - it's not a shutdown-time-only
    safety net."""
    proc = _spawn_sleeper()
    try:
        manager = BrowserManager(driver_factory=fake_factory)
        manager.acquire(browser_pid=proc.pid, timeout=0.2)

        time.sleep(0.8)

        assert proc.poll() is not None
        assert manager._sessions == {}  # cleaned up from tracking too
    finally:
        _cleanup(proc)


def test_no_watchdog_without_a_timeout():
    manager = BrowserManager(driver_factory=fake_factory)

    sb = manager.acquire()  # no timeout=

    assert manager._sessions[id(sb)].watchdog is None


def test_shutdown_cancels_outstanding_watchdogs():
    """Sessions cleaned up via shutdown() shouldn't also get killed a
    second time later by a watchdog that fires afterward."""
    proc = _spawn_sleeper()
    try:
        manager = BrowserManager(driver_factory=fake_factory)
        manager.acquire(browser_pid=proc.pid, timeout=0.3)

        manager.shutdown()  # releases it well before the watchdog would fire

        time.sleep(0.6)  # past when the (now-cancelled) watchdog would fire

        # shutdown()'s own graceful __exit__ ran, but the fake doesn't
        # touch the real process - confirm the watchdog didn't ALSO
        # try to kill it after the fact (which would be harmless here
        # since we clean up regardless, but proves cancellation works).
        assert proc.poll() is None
    finally:
        _cleanup(proc)

