from tools.base_tool import BaseTool


class VideoDownloaderTool(BaseTool):
    name = "video_downloader"
    version = "1.0.0"
    description = "Download videos from supported websites."

    def run(
        self,
        context,
        **kwargs,
    ):
        browser = context.browser
