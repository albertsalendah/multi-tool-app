from app.container import ServiceContainer
from app.execution_context import ExecutionContext
from tools.video_downloader_interactive import tool as tool_module
from tools.video_downloader_interactive.tool import VideoDownloaderInteractiveTool


class FakeBrowserManager:
    def __init__(self):
        self.acquire_calls = []
        self.release_calls = []

    def acquire(self, **options):
        self.acquire_calls.append(options)
        return object()  # a unique sentinel "session" per call

    def release(self, sb):
        self.release_calls.append(sb)


def _context_with_browser(browser, request=None) -> ExecutionContext:
    services = ServiceContainer()
    services.register("browser", browser)
    return ExecutionContext(
        tool_name="video_downloader_interactive",
        services=services,
        request=request or {},
    )


def test_validate_requires_a_non_empty_url():
    tool = VideoDownloaderInteractiveTool()

    assert tool.validate({"url": "https://example.com"}) is True
    assert tool.validate({}) is False
    assert tool.validate({"url": ""}) is False


def test_initialize_acquires_a_visible_session_with_expected_options():
    tool = VideoDownloaderInteractiveTool()
    browser = FakeBrowserManager()
    context = _context_with_browser(browser)

    tool.initialize(context)

    assert len(browser.acquire_calls) == 1
    options = browser.acquire_calls[0]
    # Visible window: a human needs to see it for manual CAPTCHA solving.
    assert options["headless"] is False
    assert options["uc"] is True
    # Required for stream_extractor's network-log sniffing to work at all.
    assert options["log_cdp"] is True


def test_initialize_stores_the_session_on_context_not_self():
    """The registry keeps ONE shared tool instance across every
    execution - storing per-run state on self would race if two
    interactive jobs ran concurrently."""
    tool = VideoDownloaderInteractiveTool()
    browser_a = FakeBrowserManager()
    browser_b = FakeBrowserManager()
    context_a = _context_with_browser(browser_a)
    context_b = _context_with_browser(browser_b)

    tool.initialize(context_a)
    tool.initialize(context_b)

    sb_a = context_a.get_state("sb")
    sb_b = context_b.get_state("sb")

    assert sb_a is not None
    assert sb_b is not None
    assert sb_a is not sb_b
    assert not hasattr(tool, "_sb")  # no per-run state on the instance


def test_run_delegates_to_the_pipeline_with_the_acquired_session():
    tool = VideoDownloaderInteractiveTool()
    browser = FakeBrowserManager()
    context = _context_with_browser(browser, request={"url": "https://example.com/watch"})
    tool.initialize(context)

    captured = {}

    def fake_run_detection(sb, url, context=None):
        captured["sb"] = sb
        captured["url"] = url
        captured["context"] = context
        return {"title": "Detected"}

    original = tool_module.run_detection
    tool_module.run_detection = fake_run_detection
    try:
        result = tool.run(context=context, url="https://example.com/watch")
    finally:
        tool_module.run_detection = original

    assert result == {"title": "Detected"}
    assert captured["sb"] is context.get_state("sb")
    assert captured["url"] == "https://example.com/watch"
    assert captured["context"] is context


def test_cleanup_releases_the_acquired_session():
    tool = VideoDownloaderInteractiveTool()
    browser = FakeBrowserManager()
    context = _context_with_browser(browser)
    tool.initialize(context)
    sb = context.get_state("sb")

    tool.cleanup(context)

    assert browser.release_calls == [sb]


def test_cleanup_is_a_noop_if_initialize_never_ran():
    tool = VideoDownloaderInteractiveTool()
    browser = FakeBrowserManager()
    context = _context_with_browser(browser)

    tool.cleanup(context)  # should not raise

    assert browser.release_calls == []


def test_cleanup_is_a_noop_with_no_context():
    tool = VideoDownloaderInteractiveTool()

    tool.cleanup(None)  # should not raise
