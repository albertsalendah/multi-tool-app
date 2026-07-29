import json
import re
import time
from typing import Dict, Optional, Tuple

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