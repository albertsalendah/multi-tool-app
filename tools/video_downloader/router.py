from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from tools.video_downloader.selenium_detector import (
    get_session_status,
    start_session,
)

# tools/video_downloader/router.py -> tools/video_downloader -> tools -> repo
# root, then /static. (Previously missing one .parent - pointed at the
# nonexistent tools/static and made GET /tools/video-downloader 500.)
STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"

router = APIRouter(prefix="/tools/video-downloader", tags=["video-downloader"])


@router.get("")
async def layout():
    return FileResponse(STATIC_DIR / "video_downloader.html")


# The fast info-lookup path (formerly GET /info here) now goes through the
# Kernel via POST /api/v1/tools/video_downloader/run - see
# tools/video_downloader/tool.py and static/app.js. This router now only
# serves the page and the interactive/CAPTCHA session endpoints below,
# which still bypass the Kernel - reconciling those is a separate, larger
# piece of work (see docs/ARCHITECTURE_CHANGELOG.md's technical debt list).


# --------------------------------------------------------------------------
# Direct Route Mapping (No wrapper functions needed)
# --------------------------------------------------------------------------

# 1. Map POST /detect-interactive directly to start_session
router.post("/detect-interactive")(start_session)

# 2. Map GET /session/{session_id}/status directly to get_session_status
router.get("/session/{session_id}/status")(get_session_status)

