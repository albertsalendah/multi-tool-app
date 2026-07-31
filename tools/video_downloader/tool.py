from tools.base_tool import BaseTool
from tools.video_downloader.extractor import VideoInfoError, fetch_video_info


class VideoDownloaderTool(BaseTool):
    name = "video_downloader"
    version = "1.0.0"
    description = (
        "Look up video/quality info from a source URL (yt-dlp based, "
        "no browser required)."
    )

    def validate(self, request) -> bool:
        return bool(request.get("url"))

    def run(self, *, context=None, **kwargs):
        url = kwargs.get("url")

        try:
            return fetch_video_info(url)
        except VideoInfoError as exc:
            # Re-raised as a plain RuntimeError so it surfaces the same
            # way any other tool failure does through kernel.run_tool()
            # (job.error for background jobs, HTTP 400/500 for the
            # synchronous /tools/{name}/run endpoint) without leaking
            # this tool's own exception type as public API.
            raise RuntimeError(str(exc)) from exc
