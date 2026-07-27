import yt_dlp


class VideoInfoError(Exception):
    """Raised when a source URL can't be read (unsupported site, dead link,
    network failure, etc). Routers translate this into a clean 4xx response
    instead of a 500."""


def fetch_video_info(url: str) -> dict:
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            raw = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise VideoInfoError(f"Could not read that URL: {exc}") from exc

    duration = raw.get("duration")

    return {
        "title": raw.get("title"),
        "thumbnail": raw.get("thumbnail"),
        "duration": duration,
        "duration_string": raw.get("duration_string") or _format_duration(duration),
        "extractor": raw.get("extractor_key"),
        "formats": _select_formats(raw.get("formats") or []),
    }


def _format_duration(seconds):
    if not seconds:
        return None
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _select_formats(raw_formats):
    """Video-capable formats only, one entry per resolution (prefers the
    variant with a known filesize), sorted best-first."""
    best_by_res = {}
    for f in raw_formats:
        if f.get("vcodec") in (None, "none"):
            continue  # audio-only stream, not a "quality to download"

        height = f.get("height")
        key = height or f.get("format_note") or f.get("format_id")
        size = f.get("filesize") or f.get("filesize_approx")
        existing = best_by_res.get(key)

        if existing is None or (size and not existing["_size"]):
            best_by_res[key] = {
                "format_id": f.get("format_id"),
                "ext": f.get("ext"),
                "resolution": f.get("format_note")
                or (f"{f.get('width')}x{height}" if height else "unknown"),
                "has_audio": f.get("acodec") not in (None, "none"),
                "filesize_display": _human_size(size),
                "_size": size,
                "_height": height or 0,
            }

    formats = sorted(best_by_res.values(), key=lambda x: x["_height"], reverse=True)
    for f in formats:
        f.pop("_size", None)
        f.pop("_height", None)
    return formats


def _human_size(num_bytes):
    if not num_bytes:
        return "Unknown"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
