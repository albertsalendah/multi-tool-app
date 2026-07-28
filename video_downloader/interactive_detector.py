import asyncio
import base64
import re
import uuid
from typing import Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from patchright.async_api import async_playwright

try:
    from video_downloader.extractor import fetch_video_info
except ImportError:
    def fetch_video_info(url, headers=None, cookies=None):
        return {
            "title": "Stream Captured",
            "duration_string": "Live / Stream",
            "extractor": "Generic Stream",
            "formats": [
                {
                    "resolution": "Auto / Stream",
                    "ext": "m3u8",
                    "has_audio": True,
                    "filesize_display": "Unknown",
                }
            ],
            "audio_formats": [],
        }


router = APIRouter()

SESSIONS: Dict[str, dict] = {}

PLAY_SELECTORS = [
    "video",
    "iframe",
    ".vjs-big-play-button",
    ".plyr__control--overlaid",
    "button[aria-label*='play' i]",
    "[class*='play-button']",
    "[class*='play_button']",
    "#player",
    ".play-btn",
    "#jwplayer",
    ".jw-video",
    "div[class*='player']",
]

STREAM_PATTERNS = [
    r"\.m3u8(\?|$)",
    r"\.mpd(\?|$)",
    r"\.mp4(\?|$)",
    r"/manifest/",
    r"/playlist/",
    r"/hls/",
]


class ClickRequest(BaseModel):
    x: int
    y: int


async def try_auto_click_play(page):
    """Attempts to trigger video playback on main page and all frames."""
    for selector in PLAY_SELECTORS:
        try:
            locator = page.locator(selector).first
            if await locator.count() and await locator.is_visible():
                await locator.click(timeout=500)
                return
        except Exception:
            continue

    for frame in page.frames:
        for selector in PLAY_SELECTORS:
            try:
                locator = frame.locator(selector).first
                if await locator.count() and await locator.is_visible():
                    await locator.click(timeout=500)
                    return
            except Exception:
                continue


async def capture_screen(page, session):
    """Helper function to safely capture and assign base64 screenshots."""
    try:
        screenshot_bytes = await page.screenshot(type="jpeg", quality=55)
        session["screenshot"] = base64.b64encode(screenshot_bytes).decode("utf-8")
    except Exception:
        pass


async def run_detection_task(session_id: str, target_url: str):
    session = SESSIONS[session_id]

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir="./patchright_session",
            headless=True,
            viewport={"width": 1280, "height": 720},
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        page = context.pages[0] if context.pages else await context.new_page()
        session["page"] = page

        captured_streams = []

        async def handle_response(response):
            url = response.url
            if url.endswith(".ts") or ".ts?" in url:
                return

            is_stream = any(re.search(pat, url, re.IGNORECASE) for pat in STREAM_PATTERNS)
            content_type = response.headers.get("content-type", "")

            if is_stream or "mpegurl" in content_type or "dash+xml" in content_type:
                if not any(s["stream_url"] == url for s in captured_streams):
                    captured_streams.append({
                        "stream_url": url,
                        "referer": response.request.headers.get("referer", target_url),
                    })

        context.on("response", handle_response)

        try:
            # Begin navigation
            goto_task = asyncio.create_task(
                page.goto(target_url, wait_until="commit", timeout=60000)
            )

            # Wait briefly and take initial screenshot immediately so canvas isn't blank
            await asyncio.sleep(1.0)
            await capture_screen(page, session)
            await goto_task

            step = 0
            # Infinite loop: keeps running until video stream captured or cancelled
            while True:
                if session.get("status") in ["completed", "failed", "cancelled"]:
                    break

                if captured_streams:
                    stream_url = captured_streams[0]["stream_url"]
                    referer = captured_streams[0]["referer"]

                    cookies = await context.cookies()
                    cookie_dict = {c["name"]: c["value"] for c in cookies}

                    try:
                        session["result"] = fetch_video_info(
                            stream_url,
                            headers={"Referer": referer},
                            cookies=cookie_dict,
                        )
                    except Exception:
                        session["result"] = {
                            "title": await page.title(),
                            "duration_string": "Stream Captured",
                            "extractor": "Generic Stream",
                            "formats": [{
                                "resolution": "Auto / Stream",
                                "ext": "m3u8" if ".m3u8" in stream_url else "mp4",
                                "has_audio": True,
                                "filesize_display": "Unknown",
                            }],
                            "audio_formats": [],
                        }

                    session["status"] = "completed"
                    break

                # Periodic auto-play click attempt once past security challenge
                page_title = (await page.title()).lower()
                is_cf_challenge = any(
                    phrase in page_title
                    for phrase in ["just a moment", "verifying", "cloudflare", "attention required"]
                )

                if step % 2 == 0 and not is_cf_challenge:
                    await try_auto_click_play(page)

                await capture_screen(page, session)

                step += 1
                await asyncio.sleep(0.8)

        except Exception as e:
            session["status"] = "failed"
            session["error"] = str(e)

        finally:
            await context.close()


@router.post("/detect-interactive")
async def start_session(url: str):
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = {
        "status": "active",
        "screenshot": "",
        "page": None,
        "result": None,
        "error": None,
    }

    asyncio.create_task(run_detection_task(session_id, url))
    return {"session_id": session_id}


@router.get("/session/{session_id}/status")
async def get_session_status(session_id: str):
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    s = SESSIONS[session_id]
    return {
        "status": s["status"],
        "screenshot": s["screenshot"],
        "result": s["result"],
        "error": s["error"],
    }


@router.post("/session/{session_id}/click")
async def send_click(session_id: str, req: ClickRequest):
    if session_id not in SESSIONS or not SESSIONS[session_id]["page"]:
        raise HTTPException(status_code=404, detail="Active page session not found")

    page = SESSIONS[session_id]["page"]
    try:
        await page.mouse.click(req.x, req.y)
    except Exception as err:
        print(f"Click error: {err}")
    return {"status": "ok"}