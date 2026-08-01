from tools.base_tool import BaseTool
from tools.video_downloader_interactive.pipeline import run_detection

# log_cdp=True is required for stream_extractor's network-log sniffing
# (driver.get_log("performance")) to have anything to read. uc/ad_block/
# slow match what the previous (broken) pipeline already used.
_SB_OPTIONS = {
    "uc": True,
    "slow": 0.5,
    "ad_block": True,
    "log_cdp": True,
}


class VideoDownloaderInteractiveTool(BaseTool):
    name = "video_downloader_interactive"
    version = "1.0.0"
    description = (
        "Open a visible browser to get past CAPTCHA/bot-detection "
        "challenges, then detect the underlying video stream."
    )

    def validate(self, request) -> bool:
        return bool(request.get("url"))

    def initialize(self, context=None):
        # headless=False: a human needs to actually see the window to
        # solve a manual CAPTCHA challenge. Session is stored on the
        # per-execution context (not self) - the registry keeps one
        # shared tool instance across every execution, so per-run state
        # has to live somewhere that isn't shared across concurrent runs.
        sb = context.browser.acquire(headless=False, **_SB_OPTIONS)
        context.set_state("sb", sb)

    def run(self, *, context=None, **kwargs):
        url = kwargs.get("url")
        sb = context.get_state("sb")
        return run_detection(sb, url, context=context)

    def cleanup(self, context=None):
        if context is None:
            return

        sb = context.get_state("sb")
        if sb is not None:
            context.browser.release(sb)
