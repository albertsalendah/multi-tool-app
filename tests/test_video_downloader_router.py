from fastapi import FastAPI
from fastapi.testclient import TestClient

from tools.video_downloader.router import router


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


def test_interactive_session_routes_no_longer_exist():
    """The interactive/CAPTCHA path now goes through POST /api/v1/jobs +
    GET /api/v1/jobs/{id} (see app/api.py, tools/video_downloader_interactive/,
    static/app.js) instead of this router's old bespoke session endpoints.
    selenium_detector.py (which these used to be mapped to) was deleted -
    its working replacement lives in tools/video_downloader_interactive/."""
    client = _client()

    response = client.post(
        "/tools/video-downloader/detect-interactive",
        params={"url": "https://example.com"},
    )
    assert response.status_code == 404

    response = client.get("/tools/video-downloader/session/some-id/status")
    assert response.status_code == 404
