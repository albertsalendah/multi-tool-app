import asyncio
import uuid
from typing import Dict

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from seleniumbase import Driver
from seleniumbase import SB

# from video_downloader.captcha_solver import resolve_captcha_and_access
from video_downloader.stream_extractor import extract_stream_from_logs
from captcha_manager import CaptchaManager

SESSIONS: Dict[str, dict] = {}


def run_detection_pipeline(session_id: str, target_url: str):
    with SB(uc=True, headless=False, slow=0.5, ad_block=True) as sb:
        sb.activate_cdp_mode()
        print("[+] Opening visible browser window in Pure CDP Mode...")
        # Open target site
        sb.goto(target_url)

        captcha = CaptchaManager(sb)

        result = captcha.check()

        if result.detected:

            if result.manual_required:
                print("Waiting for manual solve...")

                while True:
                    result = captcha.check(solve=False)
                    if not result.remaining:
                        break
            elif result.solved:
                print("CAPTCHA passed")
            else:
                print("Blocked")


#     session = SESSIONS[session_id]
#     driver = None

#     try:
#         # 1. Launch Undetected ChromeDriver with CDP Logging enabled
#         driver = Driver(
#             uc=True,
#             log_cdp=True,
#             headless=False,
#             no_sandbox=True,
#         )

#         # 2. Captcha Stage: SB Automated -> Interactive Fallback (no timeout)
#         resolve_captcha_and_access(driver, target_url)

#         # 3. Stream Extraction Stage: Network Sniffing
#         result, stream_url = extract_stream_from_logs(driver, target_url)

#         session["result"] = result
#         session["status"] = "completed"

#     except Exception as e:
#         session["status"] = "failed"
#         session["error"] = str(e)
#     finally:
#         if driver:
#             try:
#                 driver.quit()
#             except Exception:
#                 pass


async def start_session(url: str) -> dict:
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = {
        "status": "active",
        "result": None,
        "error": None,
    }

    asyncio.create_task(run_in_threadpool(run_detection_pipeline, session_id, url))
    return {"session_id": session_id}


def get_session_status(session_id: str) -> dict:
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    s = SESSIONS[session_id]
    return {
        "status": s["status"],
        "result": s["result"],
        "error": s["error"],
    }
