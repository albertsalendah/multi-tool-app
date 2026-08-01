from app.browser_manager import BrowserManager


class FakeSession:
    """Mimics what SB(...) actually returns: a context manager whose
    __enter__ yields the driver (here, itself) and whose __exit__ tears
    it down. Tracks calls so tests can assert on them."""

    def __init__(self, **options):
        self.options = options
        self.entered = False
        self.exit_count = 0
        self.raise_on_exit = False

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
