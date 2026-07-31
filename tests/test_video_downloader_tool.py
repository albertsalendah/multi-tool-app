from tools.video_downloader import tool as tool_module
from tools.video_downloader.extractor import VideoInfoError
from tools.video_downloader.tool import VideoDownloaderTool


def _patch_fetch_video_info(fake):
    original = tool_module.fetch_video_info
    tool_module.fetch_video_info = fake
    return original


def _restore_fetch_video_info(original):
    tool_module.fetch_video_info = original


def test_validate_requires_a_non_empty_url():
    tool = VideoDownloaderTool()

    assert tool.validate({"url": "https://example.com/video"}) is True
    assert tool.validate({}) is False
    assert tool.validate({"url": ""}) is False


def test_run_returns_fetch_video_info_result_unchanged():
    tool = VideoDownloaderTool()
    canned = {"title": "Example", "duration_string": "3:45", "formats": []}

    def fake_fetch(url, headers=None, cookies=None):
        assert url == "https://example.com/video"
        return canned

    original = _patch_fetch_video_info(fake_fetch)
    try:
        assert tool.run(url="https://example.com/video") == canned
    finally:
        _restore_fetch_video_info(original)


def test_run_wraps_video_info_error_as_runtime_error():
    tool = VideoDownloaderTool()

    def fake_fetch(url, headers=None, cookies=None):
        raise VideoInfoError("unsupported site")

    original = _patch_fetch_video_info(fake_fetch)
    try:
        try:
            tool.run(url="https://bad.example.com")
        except RuntimeError as exc:
            assert "unsupported site" in str(exc)
            # It should be a plain RuntimeError, not VideoInfoError leaking
            # out as this tool's own exception type.
            assert type(exc) is RuntimeError
        else:
            raise AssertionError("Expected RuntimeError.")
    finally:
        _restore_fetch_video_info(original)


def test_manifest_capabilities_no_longer_include_browser_or_filesystem():
    """Regression check: the fast lookup path needs neither, and
    over-declaring capabilities would make permission checks lie about
    what this tool actually touches."""
    import json
    from pathlib import Path

    manifest_path = Path(__file__).resolve().parent.parent / "tools" / "video_downloader" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())

    assert manifest["capabilities"] == ["network"]
