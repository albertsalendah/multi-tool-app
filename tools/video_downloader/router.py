from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

# tools/video_downloader/router.py -> tools/video_downloader -> tools -> repo
# root, then /static. (Previously missing one .parent - pointed at the
# nonexistent tools/static and made GET /tools/video-downloader 500.)
STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"

router = APIRouter(prefix="/tools/video-downloader", tags=["video-downloader"])


@router.get("")
async def layout():
    return FileResponse(STATIC_DIR / "video_downloader.html")


# Both the fast info-lookup path (formerly GET /info) and the interactive/
# CAPTCHA path (formerly POST /detect-interactive + GET
# /session/{id}/status) now go entirely through the Kernel - see
# app/api.py's POST /tools/{name}/run and POST/GET /jobs, and
# static/app.js. This router now only serves the page itself.

