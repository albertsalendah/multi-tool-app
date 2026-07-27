from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from video_downloader.extractor import VideoInfoError, fetch_video_info

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

router = APIRouter(prefix="/tools/video-downloader", tags=["video-downloader"])


@router.get("")
async def layout():
    """Serves the tool's page."""
    return FileResponse(STATIC_DIR / "video_downloader.html")


@router.get("/info")
def get_info(url: str = Query(..., description="Source video URL")):
    """Read-only lookup: title, duration, thumbnail, available qualities.
    Deliberately a plain `def` — yt-dlp's network calls block, and FastAPI
    only offloads sync path functions to its thread pool automatically.
    No download happens here; that's the next endpoint to add."""
    try:
        return fetch_video_info(url)
    except VideoInfoError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
