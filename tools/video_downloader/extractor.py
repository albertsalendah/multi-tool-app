import re
from urllib.parse import urlparse

import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


class VideoInfoError(Exception):
    """Raised when a source URL can't be read (unsupported site, dead link,
    network failure, etc). Routers translate this into a clean 4xx response
    instead of a 500."""


def fetch_video_info(url: str, headers: dict = None, cookies: dict = None) -> dict:
    parsed = urlparse(url)
    base_origin = f"{parsed.scheme}://{parsed.netloc}"

    req_headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": f"{base_origin}/",
        "Origin": base_origin,
    }

    if headers:
        normalized = {k.lower(): v for k, v in headers.items()}

        if "user-agent" in normalized:
            req_headers["User-Agent"] = normalized["user-agent"]
        if "referer" in normalized:
            req_headers["Referer"] = normalized["referer"]
        if "origin" in normalized:
            req_headers["Origin"] = normalized["origin"]

        for k, v in headers.items():
            if k.lower() not in ("user-agent", "referer", "origin", "cookie", "host"):
                req_headers[k] = v

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "impersonate": ImpersonateTarget.from_str("chrome"),
        "extractor_args": {"generic": ["impersonate"]},
        "http_headers": req_headers,
    }

    if cookies:
        cookie_header = "; ".join([f"{k}={v}" for k, v in cookies.items()])
        ydl_opts["http_headers"]["Cookie"] = cookie_header

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            raw = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        clean_msg = ANSI_ESCAPE.sub("", str(exc)).strip()
        raise VideoInfoError(clean_msg) from exc

    duration = raw.get("duration")
    raw_formats = raw.get("formats") or []

    selected_formats = _select_formats(raw_formats, duration)

    # FALLBACK: If yt-dlp extracted a direct stream/manifest with no formats array
    if not selected_formats:
        size, is_approx = _get_size(raw, duration)
        selected_formats = [{
            "format_id": raw.get("format_id") or "0",
            "ext": raw.get("ext") or "mp4",
            "resolution": raw.get("format_note") or (f"{raw.get('height')}p" if raw.get("height") else "Auto / Best"),
            "has_audio": True,
            "filesize": size,
            "filesize_display": _human_size(size, approx=is_approx),
        }]

    return {
        "title": raw.get("title") or "Untitled Video",
        "thumbnail": raw.get("thumbnail"),
        "duration": duration,
        "duration_string": raw.get("duration_string") or _format_duration(duration),
        "extractor": raw.get("extractor_key") or "Generic",
        "formats": selected_formats,
        "audio_formats": _select_audio_formats(raw_formats, duration),
    }


def _format_duration(seconds):
    if not seconds:
        return None
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _get_size(fmt_dict: dict, duration: float = None):
    """Extracts explicit filesize or calculates approximate size from bitrate * duration."""
    size = fmt_dict.get("filesize") or fmt_dict.get("filesize_approx")
    if size:
        return size, False

    # Estimate using total bitrate (tbr) or video+audio bitrate (vbr + abr)
    tbr = fmt_dict.get("tbr") or ((fmt_dict.get("vbr") or 0) + (fmt_dict.get("abr") or 0))
    if tbr and duration:
        estimated_bytes = int(tbr * 1000 / 8 * duration)
        return estimated_bytes, True

    return None, False


def _select_formats(raw_formats, duration=None):
    """Video-capable formats only, one entry per resolution, sorted best-first."""
    best_by_res = {}
    for f in raw_formats:
        if f.get("vcodec") in (None, "none"):
            continue

        height = f.get("height")
        key = height or f.get("format_note") or f.get("format_id")
        size, is_approx = _get_size(f, duration)
        existing = best_by_res.get(key)

        if existing is None or (size and not existing["filesize"]):
            best_by_res[key] = {
                "format_id": f.get("format_id"),
                "ext": f.get("ext") or "mp4",
                "resolution": f.get("format_note")
                or (f"{f.get('width')}x{height}" if height else (f"{height}p" if height else "Auto / Best")),
                "has_audio": f.get("acodec") not in (None, "none"),
                "filesize": size,
                "filesize_display": _human_size(size, approx=is_approx),
                "_height": height or 0,
            }

    formats = sorted(best_by_res.values(), key=lambda x: x["_height"], reverse=True)
    for f in formats:
        f.pop("_height", None)
    return formats


def _select_audio_formats(raw_formats, duration=None):
    """Audio-only streams, one entry per bitrate tier, sorted best-first."""
    best_by_abr = {}
    for f in raw_formats:
        if f.get("vcodec") not in (None, "none"):
            continue
        if f.get("acodec") in (None, "none"):
            continue

        abr = f.get("abr")
        key = abr or f.get("format_id")
        size, is_approx = _get_size(f, duration)
        existing = best_by_abr.get(key)

        if existing is None or (size and not existing["filesize"]):
            best_by_abr[key] = {
                "format_id": f.get("format_id"),
                "ext": f.get("ext"),
                "bitrate_display": f"{int(abr)} kbps" if abr else "unknown bitrate",
                "filesize": size,
                "filesize_display": _human_size(size, approx=is_approx),
                "_abr": abr or 0,
            }

    formats = sorted(best_by_abr.values(), key=lambda x: x["_abr"], reverse=True)
    for f in formats:
        f.pop("_abr", None)
    return formats


def _human_size(num_bytes, approx=False):
    if not num_bytes:
        return "Unknown"
    size = float(num_bytes)
    prefix = "~" if approx else ""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{prefix}{size:.1f} {unit}"
        size /= 1024
    return f"{prefix}{size:.1f} TB"