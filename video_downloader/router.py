from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from video_downloader.extractor import VideoInfoError, fetch_video_info
# from video_downloader.headless_extractor import detect_generic_video
from video_downloader.interactive_detector import router as interactive_router

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

router = APIRouter(prefix="/tools/video-downloader", tags=["video-downloader"])

router.include_router(interactive_router)

CAPTURED_SESSIONS: Dict[str, dict] = {}


class StreamRegistration(BaseModel):
    stream_url: str
    page_url: Optional[str] = ""
    page_title: Optional[str] = ""
    headers: Dict[str, str] = {}
    cookies: Optional[str] = ""


@router.post("/register-stream")
def register_stream(data: StreamRegistration):
    session_payload = {
        "page_title": data.page_title or "Video Stream",
        "page_url": data.page_url,
        "headers": data.headers,
        "cookies": _parse_cookie_str(data.cookies),
    }

    CAPTURED_SESSIONS[data.stream_url] = session_payload

    if data.page_url:
        page_domain = urlparse(data.page_url).netloc
        CAPTURED_SESSIONS[page_domain] = session_payload

    print(f"\n[EXTENSION CAPTURE] 🎬 {data.page_title}")
    print(f"  └─ Stream URL: {data.stream_url[:80]}...")
    print(f"  └─ Page URL:   {data.page_url}\n")

    return {"status": "registered", "stream_url": data.stream_url}


@router.get("/recent-streams")
def get_recent_streams():
    captured = []
    for url, session in CAPTURED_SESSIONS.items():
        if url.startswith("http"):
            captured.append({
                "stream_url": url,
                "page_title": session.get("page_title", "Unknown Video"),
                "domain": urlparse(url).netloc,
                "has_cookies": bool(session.get("cookies")),
            })
    return captured


@router.get("")
async def layout():
    return FileResponse(STATIC_DIR / "video_downloader.html")


@router.get("/info")
def get_info(url: str = Query(..., description="Source video URL")):
    headers = None
    cookies = None

    domain = urlparse(url).netloc
    if url in CAPTURED_SESSIONS:
        headers = CAPTURED_SESSIONS[url]["headers"]
        cookies = CAPTURED_SESSIONS[url]["cookies"]
    elif domain in CAPTURED_SESSIONS:
        headers = CAPTURED_SESSIONS[domain]["headers"]
        cookies = CAPTURED_SESSIONS[domain]["cookies"]

    try:
        return fetch_video_info(url, headers=headers, cookies=cookies)
    except VideoInfoError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch video info: {exc}"
        ) from exc


@router.get("/detect")
def get_detect(url: str = Query(..., description="Source video URL")):
    try:
        return detect_generic_video(url)
    except VideoInfoError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Detection error: {exc}"
        ) from exc


def _parse_cookie_str(cookie_str: str) -> dict:
    if not cookie_str:
        return {}
    out = {}
    for item in cookie_str.split(";"):
        if "=" in item:
            k, v = item.strip().split("=", 1)
            out[k] = v
    return out