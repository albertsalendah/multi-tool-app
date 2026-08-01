import json
import time

from tools.video_downloader_interactive import stream_extractor as stream_extractor_module
from tools.video_downloader_interactive.stream_extractor import extract_stream_from_logs


def _perf_entry(url: str, method: str = "Network.responseReceived") -> dict:
    return {
        "message": json.dumps(
            {
                "message": {
                    "method": method,
                    "params": {"response": {"url": url}},
                }
            }
        )
    }


class FakeDriver:
    def __init__(self, log_batches, cookies=None, title="Fake Page"):
        # Each call to get_log("performance") returns the next batch,
        # then empty lists forever - mimics polling a live log buffer.
        self._batches = list(log_batches)
        self.cookies = cookies or []
        self.title = title

    def get_log(self, log_type):
        assert log_type == "performance"
        if self._batches:
            return self._batches.pop(0)
        return []

    def get_cookies(self):
        return self.cookies


def _patch_fetch_video_info(fake):
    original = stream_extractor_module.fetch_video_info
    stream_extractor_module.fetch_video_info = fake
    return original


def _restore_fetch_video_info(original):
    stream_extractor_module.fetch_video_info = original


def test_finds_an_m3u8_stream_and_returns_fetch_video_info_result():
    driver = FakeDriver(
        log_batches=[[_perf_entry("https://cdn.example.com/video/master.m3u8?token=abc")]],
        cookies=[{"name": "session", "value": "xyz"}],
    )
    canned = {"title": "Real Title", "formats": []}

    def fake_fetch(url, headers=None, cookies=None):
        assert url == "https://cdn.example.com/video/master.m3u8?token=abc"
        assert headers == {"Referer": "https://example.com/watch"}
        assert cookies == {"session": "xyz"}
        return canned

    original = _patch_fetch_video_info(fake_fetch)
    try:
        result, stream_url = extract_stream_from_logs(
            driver, "https://example.com/watch", max_wait=5
        )
        assert result == canned
        assert stream_url == "https://cdn.example.com/video/master.m3u8?token=abc"
    finally:
        _restore_fetch_video_info(original)


def test_skips_ts_segment_urls_and_keeps_looking():
    driver = FakeDriver(
        log_batches=[
            [
                _perf_entry("https://cdn.example.com/seg-001.ts"),
                _perf_entry("https://cdn.example.com/master.m3u8"),
            ]
        ]
    )

    original = _patch_fetch_video_info(lambda *a, **k: {"title": "x"})
    try:
        _result, stream_url = extract_stream_from_logs(driver, "https://x", max_wait=5)
        assert stream_url == "https://cdn.example.com/master.m3u8"
    finally:
        _restore_fetch_video_info(original)


def test_ignores_unrelated_network_events():
    driver = FakeDriver(
        log_batches=[
            [
                _perf_entry("https://example.com/page.js"),
                _perf_entry("https://example.com/style.css"),
                _perf_entry("https://cdn.example.com/stream.mp4"),
            ]
        ]
    )

    original = _patch_fetch_video_info(lambda *a, **k: {"title": "x"})
    try:
        _result, stream_url = extract_stream_from_logs(driver, "https://x", max_wait=5)
        assert stream_url == "https://cdn.example.com/stream.mp4"
    finally:
        _restore_fetch_video_info(original)


def test_raises_when_nothing_found_within_max_wait():
    driver = FakeDriver(log_batches=[])

    start = time.monotonic()
    try:
        extract_stream_from_logs(driver, "https://x", max_wait=0.5)
    except RuntimeError as exc:
        assert "No stream URL" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError.")

    # Should respect max_wait, not hang indefinitely.
    assert time.monotonic() - start < 3


def test_falls_back_to_synthetic_result_when_fetch_video_info_raises():
    driver = FakeDriver(
        log_batches=[[_perf_entry("https://cdn.example.com/master.m3u8")]],
        title="Captured Page Title",
    )

    def fake_fetch_raises(url, headers=None, cookies=None):
        raise RuntimeError("yt-dlp couldn't parse this manifest")

    original = _patch_fetch_video_info(fake_fetch_raises)
    try:
        result, stream_url = extract_stream_from_logs(driver, "https://x", max_wait=5)

        # Falls back to a synthetic result built from what we do know,
        # rather than failing the whole detection over a metadata miss.
        assert result["title"] == "Captured Page Title"
        assert result["formats"][0]["ext"] == "m3u8"
        assert stream_url == "https://cdn.example.com/master.m3u8"
    finally:
        _restore_fetch_video_info(original)


def test_malformed_log_entries_are_skipped_without_crashing():
    driver = FakeDriver(
        log_batches=[
            [
                {"message": "not valid json"},
                _perf_entry("https://cdn.example.com/master.m3u8"),
            ]
        ]
    )

    original = _patch_fetch_video_info(lambda *a, **k: {"title": "x"})
    try:
        _result, stream_url = extract_stream_from_logs(driver, "https://x", max_wait=5)
        assert stream_url == "https://cdn.example.com/master.m3u8"
    finally:
        _restore_fetch_video_info(original)
