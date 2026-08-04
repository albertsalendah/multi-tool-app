import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import router as platform_api_router
from app.kernel import ApplicationKernel
from tools.video_downloader.router import router as video_downloader_router

# --------------------------------------------------------------------------
# Suppress status polling logs from uvicorn.access
# --------------------------------------------------------------------------
class EndpointLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Check if record has arguments (record.args holds method, path, etc.)
        if record.args and len(record.args) >= 3:
            path = str(record.args[2])
            # Exclude status polling requests
            if "/session/" in path and "/status" in path:
                return False
        return True

# Apply the filter to Uvicorn's access logger
logging.getLogger("uvicorn.access").addFilter(EndpointLogFilter())
# --------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    kernel = ApplicationKernel()
    kernel.initialize()
    app.state.kernel = kernel

    yield

    kernel.shutdown()


app = FastAPI(title="Multi-Tool App", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows extension fetches
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The generic, kernel-backed platform API (GET /health, GET /tools,
# POST /jobs, GET/DELETE /jobs/{id}) - see docs/implementation/API_REFERENCE.md
app.include_router(platform_api_router)

# Each tool contributes its own router. Adding a new tool later means:
# 1. new_tool/router.py with its own APIRouter
# 2. one include_router() line here
# 3. one card in static/index.html
# No other part of this file needs to change.
#
# video_downloader_router now only serves the tool's page (GET
# /tools/video-downloader) - both the fast lookup and interactive/CAPTCHA
# paths go entirely through platform_api_router / kernel.run_tool() (see
# static/app.js and tools/video_downloader/router.py).
app.include_router(video_downloader_router)

app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


@app.get("/")
async def home():
    return FileResponse(STATIC_DIR / "index.html")
