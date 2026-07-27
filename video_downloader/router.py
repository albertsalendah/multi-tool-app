from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

router = APIRouter(prefix="/tools/video-downloader", tags=["video-downloader"])


@router.get("")
async def layout():
    """Serves the tool's page. Currently layout only — no submit/status/
    result endpoints yet (that's Phase 2: yt-dlp integration)."""
    return FileResponse(STATIC_DIR / "video_downloader.html")
