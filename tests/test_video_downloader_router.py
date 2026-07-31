import sys
import types


def _stub_selenium_detector():
    """selenium_detector.py imports seleniumbase, which isn't installed
    in every environment that should be able to run this test suite
    (it's a server-side dependency, not needed just to test routing).
    Stub it out before router.py imports it, so this file doesn't
    require installing seleniumbase just to check route wiring."""

    if "tools.video_downloader.selenium_detector" in sys.modules:
        return

    stub = types.ModuleType("tools.video_downloader.selenium_detector")

    async def start_session(url):
        return {"session_id": "stub-session"}

    def get_session_status(session_id):
        return {"status": "active", "result": None, "error": None}

    stub.start_session = start_session
    stub.get_session_status = get_session_status
    sys.modules["tools.video_downloader.selenium_detector"] = stub


_stub_selenium_detector()

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from tools.video_downloader.router import router  # noqa: E402


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_layout_serves_the_real_static_page():
    """Regression check for the STATIC_DIR bug: it was missing one
    .parent and pointed at the nonexistent tools/static, so this route
    500'd on every request before the fix."""
    client = _client()

    response = client.get("/tools/video-downloader")

    assert response.status_code == 200
    assert "Video Downloader" in response.text


def test_info_endpoint_no_longer_exists():
    """The fast lookup now goes through POST /api/v1/tools/video_downloader/run
    (see app/api.py, tools/video_downloader/tool.py, static/app.js)
    instead of this tool-specific route."""
    client = _client()

    response = client.get(
        "/tools/video-downloader/info", params={"url": "https://example.com"}
    )

    assert response.status_code == 404


def test_interactive_session_routes_are_still_registered():
    """Not testing the real (still Stage-2, still broken) detection
    pipeline here - just confirming router.py's route wiring for it
    wasn't disturbed by removing /info and fixing STATIC_DIR."""
    client = _client()

    response = client.post(
        "/tools/video-downloader/detect-interactive",
        params={"url": "https://example.com"},
    )
    assert response.status_code == 200
    assert response.json() == {"session_id": "stub-session"}

    response = client.get("/tools/video-downloader/session/stub-session/status")
    assert response.status_code == 200
    assert response.json()["status"] == "active"
