from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from video_downloader.extractor import VideoInfoError, fetch_video_info

# --- ENGINE SELECTION ---
# Switch between SeleniumBase and Patchright by changing this import:
from video_downloader.selenium_detector import (
    get_session_status,
    start_session,
)

# To switch back to Patchright Playwright, use:
# from video_downloader.interactive_detector import (
#     start_session,
#     get_session_status,
# )

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

router = APIRouter(prefix="/tools/video-downloader", tags=["video-downloader"])


@router.get("")
async def layout():
    return FileResponse(STATIC_DIR / "video_downloader.html")


@router.get("/info")
def get_info(url: str = Query(..., description="Source video URL")):
    try:
        return fetch_video_info(url)
    except VideoInfoError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch video info: {exc}"
        ) from exc


# --------------------------------------------------------------------------
# Direct Route Mapping (No wrapper functions needed)
# --------------------------------------------------------------------------

# 1. Map POST /detect-interactive directly to start_session
router.post("/detect-interactive")(start_session)

# 2. Map GET /session/{session_id}/status directly to get_session_status
router.get("/session/{session_id}/status")(get_session_status)
