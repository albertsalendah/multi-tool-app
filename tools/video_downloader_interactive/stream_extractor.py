import json
import re
import time
from typing import Dict, Optional, Tuple

from tools.video_downloader.extractor import fetch_video_info

STREAM_PATTERNS = [
    r"\.m3u8(\?|$)",
    r"\.mpd(\?|$)",
    r"\.mp4(\?|$)",
    r"/manifest/",
    r"/playlist/",
    r"/hls/",
]


def extract_stream_from_logs(driver, target_url: str, max_wait: Optional[int] = 30) -> Tuple[Dict, str]:
    """
    Purely responsible for sniffing network performance logs
    and extracting video stream links (.m3u8, .mp4) + metadata.

    Requires the driver's session to have been started with performance
    logging enabled (SeleniumBase: log_cdp=True / log_cdp_events=True) -
    otherwise get_log("performance") returns nothing to search.
    """
    captured_stream = None
    referer = target_url
    start_time = time.time()

    while True:
        if max_wait and (time.time() - start_time > max_wait):
            break

        try:
            logs = driver.get_log("performance")
            for entry in logs:
                try:
                    message = json.loads(entry["message"])["message"]
                    if message.get("method") == "Network.responseReceived":
                        resp_url = message["params"]["response"]["url"]

                        if resp_url.endswith(".ts") or ".ts?" in resp_url:
                            continue

                        if any(re.search(pat, resp_url, re.IGNORECASE) for pat in STREAM_PATTERNS):
                            captured_stream = resp_url
                            break
                except Exception:
                    continue
        except Exception:
            pass

        if captured_stream:
            break

        time.sleep(0.8)

    if not captured_stream:
        raise RuntimeError("No stream URL (.m3u8 / .mp4) detected in network traffic.")

    # Extract cookies to pass to yt-dlp extractor
    cookies = driver.get_cookies()
    cookie_dict = {c["name"]: c["value"] for c in cookies}

    try:
        result = fetch_video_info(
            captured_stream,
            headers={"Referer": referer},
            cookies=cookie_dict,
        )
    except Exception:
        # We found a real stream URL but yt-dlp couldn't pull full
        # metadata for it (e.g. an unusual manifest format) - return a
        # minimal synthetic result with what we actually know, rather
        # than failing the whole detection.
        result = {
            "title": getattr(driver, "title", "Captured Stream"),
            "duration_string": "Stream Captured",
            "extractor": "SeleniumBase Stream",
            "formats": [{
                "resolution": "Auto / Best",
                "ext": "m3u8" if ".m3u8" in captured_stream else "mp4",
                "has_audio": True,
                "filesize_display": "Unknown",
            }],
            "audio_formats": [],
        }

    return result, captured_stream
