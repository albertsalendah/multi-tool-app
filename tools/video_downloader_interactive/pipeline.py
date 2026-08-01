from libraries.captcha_manager import CaptchaManager

from tools.video_downloader_interactive.stream_extractor import extract_stream_from_logs


def run_detection(sb, url: str, context=None) -> dict:
    """
    Navigate to `url` in an already-acquired SeleniumBase session, get
    past any CAPTCHA/bot-detection challenge (automated where possible;
    manual solving needs a non-headless session - see tool.py), then
    sniff the resulting network traffic for the underlying video stream.

    Returns the same shape tools.video_downloader.extractor.fetch_video_info()
    returns. Raises RuntimeError if the challenge couldn't be cleared, or
    if no stream URL was found in network traffic within the timeout
    (see stream_extractor.extract_stream_from_logs).
    """

    # activate_cdp_mode() must run before constructing CaptchaManager -
    # it's what sets up sb.cdp / sb.solve_captcha, which
    # libraries/captcha_manager relies on (confirmed against the real
    # installed seleniumbase package, not assumed from memory).
    sb.activate_cdp_mode()
    sb.goto(url)

    if context is not None:
        context.raise_if_cancelled()

    captcha = CaptchaManager(sb)
    result = captcha.check()

    if result.detected and result.remaining:
        raise RuntimeError(
            "Could not get past the CAPTCHA/challenge on this page "
            f"(detected: {', '.join(result.types) or 'unknown'})."
        )

    if context is not None:
        context.raise_if_cancelled()

    video_info, _stream_url = extract_stream_from_logs(sb.driver, url)
    return video_info
