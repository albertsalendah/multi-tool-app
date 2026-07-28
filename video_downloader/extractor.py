# video_downloader/extractor.py
from typing import Any, Dict, Optional
import yt_dlp


class VideoInfoError(Exception):
    """Custom exception raised when video info fetching fails."""
    pass


def _human_size(num_bytes: Optional[int]) -> str:
    if not num_bytes:
        return "Unknown"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"


def fetch_video_info(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    cookies: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }

    if headers:
        ydl_opts["http_headers"] = headers

    # If cookies dictionary was passed, inject cookie string header
    if cookies and "http_headers" not in ydl_opts:
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
        ydl_opts["http_headers"] = {"Cookie": cookie_str}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                raise VideoInfoError("Could not retrieve video details.")

            # Filter formats
            formats = []
            audio_formats = []

            for fmt in info.get("formats", []):
                vcodec = fmt.get("vcodec", "none")
                acodec = fmt.get("acodec", "none")
                filesize = fmt.get("filesize") or fmt.get("filesize_approx")

                format_data = {
                    "format_id": fmt.get("format_id"),
                    "ext": fmt.get("ext", "mp4"),
                    "resolution": fmt.get("format_note") or f"{fmt.get('height', 'unknown')}p",
                    "filesize": filesize,
                    "filesize_display": _human_size(filesize),
                    "has_audio": acodec != "none",
                }

                if vcodec != "none":
                    formats.append(format_data)
                elif acodec != "none":
                    format_data["bitrate_display"] = f"{int(fmt.get('tbr', 0))} kbps"
                    audio_formats.append(format_data)

            return {
                "title": info.get("title", "Untitled"),
                "duration_string": info.get("duration_string") or f"{info.get('duration', 0)}s",
                "extractor": info.get("extractor_key", "Generic"),
                "thumbnail": info.get("thumbnail"),
                "formats": formats,
                "audio_formats": audio_formats,
            }

    except Exception as exc:
        raise VideoInfoError(f"Extraction failed: {exc}") from exc