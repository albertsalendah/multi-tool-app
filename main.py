from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from video_downloader.router import router as video_downloader_router

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Multi-Tool App")

# Each tool contributes its own router. Adding a new tool later means:
# 1. new_tool/router.py with its own APIRouter
# 2. one include_router() line here
# 3. one card in static/index.html
# No other part of this file needs to change.
app.include_router(video_downloader_router)

app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


@app.get("/")
async def home():
    return FileResponse(STATIC_DIR / "index.html")
