from app.cancellation import CancellationRequested
from app.container import ServiceContainer
from app.execution_context import ExecutionContext
from tools.video_downloader_interactive import pipeline as pipeline_module
from tools.video_downloader_interactive.pipeline import run_detection


class FakeSB:
    def __init__(self):
        self.activated = False
        self.goto_calls = []
        self.call_order = []
        self.driver = object()

    def activate_cdp_mode(self):
        self.activated = True
        self.call_order.append("activate_cdp_mode")

    def goto(self, url):
        self.goto_calls.append(url)
        self.call_order.append("goto")


class FakeCaptchaResult:
    def __init__(self, detected=False, remaining=False, types=None):
        self.detected = detected
        self.remaining = remaining
        self.types = types or []


def _patch(module, name, value):
    original = getattr(module, name)
    setattr(module, name, value)
    return original


def _restore(module, name, original):
    setattr(module, name, original)


def _context() -> ExecutionContext:
    return ExecutionContext(tool_name="video_downloader_interactive", services=ServiceContainer())


def test_activates_cdp_mode_before_navigating():
    sb = FakeSB()

    class NoOpCaptchaManager:
        def __init__(self, sb):
            pass

        def check(self, solve=True):
            return FakeCaptchaResult(detected=False)

    original_cm = _patch(pipeline_module, "CaptchaManager", NoOpCaptchaManager)
    original_extract = _patch(
        pipeline_module,
        "extract_stream_from_logs",
        lambda driver, url, **kw: ({"title": "ok"}, "https://stream"),
    )
    try:
        run_detection(sb, "https://example.com")

        assert sb.activated is True
        assert sb.goto_calls == ["https://example.com"]
        assert sb.call_order == ["activate_cdp_mode", "goto"]
    finally:
        _restore(pipeline_module, "CaptchaManager", original_cm)
        _restore(pipeline_module, "extract_stream_from_logs", original_extract)


def test_returns_stream_extractor_result_when_no_captcha_present():
    sb = FakeSB()

    class NoOpCaptchaManager:
        def __init__(self, sb):
            pass

        def check(self, solve=True):
            return FakeCaptchaResult(detected=False)

    canned = {"title": "Detected Video", "formats": []}

    original_cm = _patch(pipeline_module, "CaptchaManager", NoOpCaptchaManager)
    original_extract = _patch(
        pipeline_module,
        "extract_stream_from_logs",
        lambda driver, url, **kw: (canned, "https://stream"),
    )
    try:
        result = run_detection(sb, "https://example.com")
        assert result == canned
    finally:
        _restore(pipeline_module, "CaptchaManager", original_cm)
        _restore(pipeline_module, "extract_stream_from_logs", original_extract)


def test_raises_when_captcha_remains_unresolved():
    sb = FakeSB()

    class BlockedCaptchaManager:
        def __init__(self, sb):
            pass

        def check(self, solve=True):
            return FakeCaptchaResult(detected=True, remaining=True, types=["cloudflare"])

    original_cm = _patch(pipeline_module, "CaptchaManager", BlockedCaptchaManager)
    try:
        try:
            run_detection(sb, "https://example.com")
        except RuntimeError as exc:
            assert "cloudflare" in str(exc)
        else:
            raise AssertionError("Expected RuntimeError.")
    finally:
        _restore(pipeline_module, "CaptchaManager", original_cm)


def test_proceeds_to_extraction_when_captcha_was_solved():
    sb = FakeSB()

    class SolvedCaptchaManager:
        def __init__(self, sb):
            pass

        def check(self, solve=True):
            return FakeCaptchaResult(detected=True, remaining=False)

    extract_calls = []

    def fake_extract(driver, url, **kw):
        extract_calls.append(url)
        return {"title": "post-captcha"}, "https://stream"

    original_cm = _patch(pipeline_module, "CaptchaManager", SolvedCaptchaManager)
    original_extract = _patch(pipeline_module, "extract_stream_from_logs", fake_extract)
    try:
        result = run_detection(sb, "https://example.com")
        assert result == {"title": "post-captcha"}
        assert extract_calls == ["https://example.com"]
    finally:
        _restore(pipeline_module, "CaptchaManager", original_cm)
        _restore(pipeline_module, "extract_stream_from_logs", original_extract)


def test_respects_cancellation_before_captcha_check():
    sb = FakeSB()
    context = _context()
    context.cancellation_token.cancel()

    captcha_manager_instantiations = []

    class TrackedCaptchaManager:
        def __init__(self, sb):
            captcha_manager_instantiations.append(sb)

        def check(self, solve=True):
            return FakeCaptchaResult(detected=False)

    original_cm = _patch(pipeline_module, "CaptchaManager", TrackedCaptchaManager)
    try:
        try:
            run_detection(sb, "https://example.com", context=context)
        except CancellationRequested:
            pass
        else:
            raise AssertionError("Expected CancellationRequested.")
    finally:
        _restore(pipeline_module, "CaptchaManager", original_cm)

    # Cancellation should be caught before ever constructing CaptchaManager.
    assert captcha_manager_instantiations == []


def test_respects_cancellation_discovered_after_captcha_check():
    sb = FakeSB()
    context = _context()

    class CancelsDuringCheckCaptchaManager:
        """Simulates cancellation arriving while check() was running -
        the second raise_if_cancelled() (before stream extraction)
        should catch it."""

        def __init__(self, sb):
            pass

        def check(self, solve=True):
            context.cancellation_token.cancel()
            return FakeCaptchaResult(detected=False)

    extract_calls = []

    def fake_extract(driver, url, **kw):
        extract_calls.append(url)
        return {"title": "should not reach here"}, "https://stream"

    original_cm = _patch(pipeline_module, "CaptchaManager", CancelsDuringCheckCaptchaManager)
    original_extract = _patch(pipeline_module, "extract_stream_from_logs", fake_extract)
    try:
        try:
            run_detection(sb, "https://example.com", context=context)
        except CancellationRequested:
            pass
        else:
            raise AssertionError("Expected CancellationRequested.")
    finally:
        _restore(pipeline_module, "CaptchaManager", original_cm)
        _restore(pipeline_module, "extract_stream_from_logs", original_extract)

    assert extract_calls == []


def test_works_without_a_context():
    """context is optional (defaults to None) - e.g. for direct/manual
    invocation outside the Kernel's job lifecycle."""
    sb = FakeSB()

    class NoOpCaptchaManager:
        def __init__(self, sb):
            pass

        def check(self, solve=True):
            return FakeCaptchaResult(detected=False)

    original_cm = _patch(pipeline_module, "CaptchaManager", NoOpCaptchaManager)
    original_extract = _patch(
        pipeline_module,
        "extract_stream_from_logs",
        lambda driver, url, **kw: ({"title": "ok"}, "https://stream"),
    )
    try:
        result = run_detection(sb, "https://example.com")  # no context= at all
        assert result == {"title": "ok"}
    finally:
        _restore(pipeline_module, "CaptchaManager", original_cm)
        _restore(pipeline_module, "extract_stream_from_logs", original_extract)
