"""
CDP Screencast spike test - v3: plain-polling frame delivery (not MJPEG
push) + click-forwarding from the client's image into the real browser
session.

--------------------------------------------------------------------
Why v3 exists (context for whoever picks this up next):

v2 used a single long-lived multipart/x-mixed-replace HTTP connection
per viewer (classic "MJPEG stream"). Real testing found it works in
desktop Firefox but NOT in Chrome (desktop or Android) or Chromium-
based apps (1DM+) - confirmed via server-side logging showing the
server successfully writing frames to the wire in both cases, so the
break is entirely client-side: those browsers' <img> implementations
don't reliably handle multipart/x-mixed-replace. Since Chrome is the
dominant browser this app needs to support, v3 drops MJPEG entirely
in favor of the client polling a plain single-JPEG endpoint
(GET /frame) on an interval. This is less "real-time" than a push
stream, but works identically everywhere because it's nothing but
ordinary repeated HTTP GETs - no reliance on any browser's multipart
handling.

--------------------------------------------------------------------
Debugging notes carried over from v2 (still true, kept so they don't
get re-litigated):

- sb.cdp.loop must be explicitly pumped (see the main loop below) for
  ANY screencast frames to be processed at all - nothing drives
  mycdp's asyncio loop on its own. Plain time.sleep() leaves the frame
  counter at 0 forever, headless or not.
- Earlier headless=True testing (under the old v2 MJPEG transport)
  showed frames counting but the image staying blank, and was
  attributed to a Chromium headless-screencast rendering limitation.
  That claim turned out to be unverified and probably wrong - see the
  dedicated Headless note further down for the corrected finding.
- Page.startScreencast is repaint-triggered, not continuous - a fully
  idle page produces no further frames until something repaints. The
  capture_screenshot() seed frame exists so the modal shows something
  immediately instead of staying blank until the first repaint.

--------------------------------------------------------------------
Click-forwarding - CONFIRMED WORKING (2026-08-21):

The coordinate math (client fraction -> encoded-frame pixels ->
CSS-pixel viewport coordinates via the screencast frame's own
ScreencastFrameMetadata) was built from CDP's documented field
semantics, not a worked reference example - flagged at the time as
unverified. Since confirmed for real: full reCAPTCHA image-selection
challenges (not just the checkbox) solved successfully from desktop
Firefox, desktop Chrome, Android Chrome, and 1DM+, across two
different physical machines plus a phone over LAN. Good enough
evidence to trust the formula as correct, not just plausible.

Known limitation: clicking is ignored until the first real
ScreencastFrame arrives (its metadata is what the math needs) - the
capture_screenshot() seed frame has no accompanying metadata. In
practice this window is short, since interacting in the real window
is exactly what produces that first frame.

--------------------------------------------------------------------
Sizing (2026-08-21): the captured frame is the WHOLE page, so a small
widget on a large page renders tiny. set_window_size() below shrinks
the real browser window so the page (and the widget in it) fills more
of the frame - fixes both the "too small to use on a phone" and the
"blurry" complaints at once, since the same JPEG quality now covers
less content. This is a test-only convenience, NOT the production
answer: video_downloader_interactive runs against arbitrary
third-party sites, and forcing a small viewport there risks tripping
a site's mobile/responsive layout and changing where or whether the
CAPTCHA even renders. The real production fix is cropping the frame
to the actual CAPTCHA element's on-page bounding box (findable via
libraries/captcha_manager's existing detector/selectors), not
shrinking the window globally - not built here, real next step.

--------------------------------------------------------------------
Headless (2026-08-21): earlier debugging notes below claimed headless
screencast frames come back blank/garbage - stated with more
confidence than was earned, since that claim was never actually
checked against real frame bytes from a headless run (only
headless=False runs were ever byte-verified). Retested under this v3
polling architecture with headless=True: worked cleanly, no blank
frames. Most likely the earlier blank-under-headless observation was
actually the same Chrome/MJPEG multipart bug confirmed separately
below, not a real headless-capture problem. Matters beyond just this
script: tool.py hardcodes headless=False specifically so a human can
SEE the real window to solve a CAPTCHA - if a human can instead solve
it remotely via this screencast+click-forwarding mechanism, that
requirement goes away, and headless is exactly what's wanted for the
actual remote-server deployment target (no display to hand a window
to). Promising, but only lightly retested so far - worth a couple
more full solves under headless=True before leaning on it hard.

Requires:
  pip install seleniumbase --break-system-packages
  style.css saved in the SAME folder as this script (copy of the real
  static/style.css from the repo - ask if you don't have it handy).

Run: python3 captcha_screencast_test.py [url]
Then open http://localhost:8091 - click "Simulate: CAPTCHA required"
to open the modal, then click directly on the challenge inside the
modal image and watch the REAL SeleniumBase-opened Chrome window to
see whether the click landed in the right place.
"""

import asyncio
import base64
import json
import os
import queue
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import mycdp.input_ as cdp_input
import mycdp.page as cdp_page
from seleniumbase import SB

PORT = 8091
TARGET_URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.google.com/recaptcha/api2/demo"
CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.css")

_lock = threading.Lock()
_latest_frame = None  # raw JPEG bytes of the most recent frame
_latest_metadata = None  # the ScreencastFrameMetadata that came with it (None for the seed frame)
_frame_count = 0
_pending_clicks: "queue.Queue[tuple[float, float]]" = queue.Queue()


def _jpeg_dimensions(data: bytes):
    """Parse (width, height) straight out of the JPEG's SOF marker -
    avoids adding Pillow as a dependency just for this one thing.
    Returns None if the data doesn't parse cleanly (truncated/malformed)."""
    if data[0:2] != b"\xff\xd8":
        return None
    i = 2
    n = len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker in (0xD8, 0xD9, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker in (0xC0, 0xC1, 0xC2, 0xC3):  # SOF0-3 (baseline/progressive)
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
            return width, height
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        i += 2 + length
    return None


class StreamHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # quiet - don't spam the console per request

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            self._serve_index()
        elif path == "/assets/style.css":
            self._serve_css()
        elif path == "/frame":
            self._serve_frame()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlsplit(self.path).path
        if path == "/click":
            self._handle_click()
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_css(self):
        with open(CSS_PATH, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/css")
        self.end_headers()
        self.wfile.write(body)

    def _serve_frame(self):
        with _lock:
            frame = _latest_frame
        if frame is None:
            self.send_response(503)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(frame)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(frame)

    def _handle_click(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length))
            frac_x = float(payload["frac_x"])
            frac_y = float(payload["frac_y"])
        except (ValueError, KeyError, TypeError):
            self.send_response(400)
            self.end_headers()
            return

        _pending_clicks.put((frac_x, frac_y))
        self.send_response(204)
        self.end_headers()

    def _serve_index(self):
        # This is the real static/video_downloader.html markup, unmodified,
        # plus one test-only button and the modal overlay wired to the
        # live stream - so the UI you're judging is the real one, not an
        # approximation of it. The modal reuses the existing (currently
        # unused in the real app) .modal-overlay/.canvas-wrapper/
        # .canvas-loader CSS classes from static/style.css directly.
        body = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Video Downloader — Multi-Tool</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/assets/style.css">
</head>
<body>
  <div class="page">
    <a class="back-link" href="#">&larr; Toolkit</a>

    <header class="page-header">
      <span class="eyebrow">TOOL // 01</span>
      <h1>Video Downloader</h1>
      <p class="subtitle">Paste a source URL, pick a destination, submit.</p>
    </header>

    <main class="tool-layout">
      <form class="tool-form" id="info-form">
        <label for="url">Source URL</label>
        <input id="url" name="url" type="url" placeholder="https://..." required>

        <label for="destination">Destination</label>
        <select id="destination" disabled>
          <option>Google Drive</option>
          <option>Mega.nz</option>
          <option>Yandex Disk</option>
        </select>

        <button type="submit" id="fetch-btn">Fetch details</button>
      </form>

      <p class="error" id="error" hidden></p>
      <button class="secondary-btn" id="detect-btn">Try generic detection (slower)</button>

      <button class="secondary-btn" id="simulate-btn" style="margin-top:8px;border-color:#e8a33d;color:#e8a33d;">
        Simulate: CAPTCHA required (test-only button, not part of the real app)
      </button>
    </main>
  </div>

  <div class="modal-overlay" id="captcha-modal" hidden>
    <div class="modal-card">
      <div class="modal-header">
        <h3>Manual verification required</h3>
        <span class="modal-subtitle">Solve the challenge below to continue. Click directly on it - clicks are forwarded to the real browser session.</span>
      </div>
      <div class="canvas-wrapper">
        <img id="stream-canvas" src="" alt="Live CAPTCHA stream">
        <span class="canvas-loader" id="canvas-loader">Waiting for stream...</span>
      </div>
      <div style="margin-top:14px;display:flex;justify-content:flex-end;gap:8px;">
        <button class="secondary-btn" id="cancel-btn">Cancel job</button>
      </div>
    </div>
  </div>

  <script>
    const modal = document.getElementById('captcha-modal');
    const streamImg = document.getElementById('stream-canvas');
    const loader = document.getElementById('canvas-loader');
    const POLL_MS = 300;
    let pollHandle = null;
    let firstFrameShown = false;

    function pollFrame() {
      streamImg.src = '/frame?t=' + Date.now();  // cache-bust each poll
    }

    document.getElementById('simulate-btn').addEventListener('click', () => {
      modal.hidden = false;
      loader.hidden = false;
      firstFrameShown = false;
      pollFrame();
      pollHandle = setInterval(pollFrame, POLL_MS);
    });

    streamImg.addEventListener('load', () => {
      firstFrameShown = true;
      loader.hidden = true;
    });

    // object-fit: contain means the actual rendered image content may
    // be letterboxed inside the element's box - a click's position has
    // to be measured against that inner content rect, not the element's
    // full bounding box, or coordinates near the edges would be wrong.
    function imageContentRect(img) {
      const box = img.getBoundingClientRect();
      const boxRatio = box.width / box.height;
      const imgRatio = img.naturalWidth / img.naturalHeight;
      let width, height, offsetX, offsetY;
      if (imgRatio > boxRatio) {
        width = box.width;
        height = box.width / imgRatio;
        offsetX = 0;
        offsetY = (box.height - height) / 2;
      } else {
        height = box.height;
        width = box.height * imgRatio;
        offsetY = 0;
        offsetX = (box.width - width) / 2;
      }
      return { box, width, height, offsetX, offsetY };
    }

    streamImg.addEventListener('click', (e) => {
      if (!firstFrameShown) return;
      const { box, width, height, offsetX, offsetY } = imageContentRect(streamImg);
      const x = e.clientX - box.left - offsetX;
      const y = e.clientY - box.top - offsetY;
      if (x < 0 || y < 0 || x > width || y > height) return;  // clicked the letterbox bar, not the image

      fetch('/click', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ frac_x: x / width, frac_y: y / height }),
      });
    });

    document.getElementById('cancel-btn').addEventListener('click', () => {
      modal.hidden = true;
      if (pollHandle) clearInterval(pollHandle);
      streamImg.src = '';
      loader.hidden = false;
      console.log('Cancel clicked - in the real app this would cancel the job via DELETE /api/v1/jobs/{id}.');
    });
  </script>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode())


def run_server():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), StreamHandler)
    server.serve_forever()


async def on_frame(event, connection):
    """CDP event handler - fires once per screencast frame. Confirmed
    against the real ScreencastFrame dataclass: .data is base64 JPEG,
    .metadata is the ScreencastFrameMetadata used for click-coordinate
    translation below, .session_id must be echoed back in the ack or
    Chrome stalls the stream waiting for acknowledgement."""
    global _latest_frame, _latest_metadata, _frame_count

    with _lock:
        _latest_frame = base64.b64decode(event.data)
        _latest_metadata = event.metadata
        _frame_count += 1
        count = _frame_count

    # Debug-only: dump the first few real frames to disk so they can be
    # inspected directly, independent of the serving/browser-decode path.
    if count <= 3:
        with open(f"frame_{count}.jpg", "wb") as f:
            f.write(_latest_frame)

    await connection.send(cdp_page.screencast_frame_ack(session_id=event.session_id))


def _dispatch_click(sb, frac_x: float, frac_y: float):
    """Translate a click reported as a fraction of the displayed frame
    into real CSS-pixel viewport coordinates and forward it into the
    live session via CDP. See the module docstring's click-forwarding
    section - this math is unverified against a real live session."""
    with _lock:
        frame = _latest_frame
        metadata = _latest_metadata

    if frame is None or metadata is None:
        print("[click] ignored - no frame/metadata yet")
        return

    dims = _jpeg_dimensions(frame)
    if dims is None:
        print("[click] ignored - could not parse frame dimensions")
        return

    frame_w, frame_h = dims
    scale_x = metadata.device_width / frame_w
    scale_y = metadata.device_height / frame_h
    page_scale = metadata.page_scale_factor or 1.0

    viewport_x = (frac_x * frame_w * scale_x) / page_scale
    viewport_y = ((frac_y * frame_h * scale_y) - metadata.offset_top) / page_scale

    print(
        f"[click] frac=({frac_x:.3f}, {frac_y:.3f}) frame={frame_w}x{frame_h} "
        f"device={metadata.device_width:.0f}x{metadata.device_height:.0f} "
        f"-> viewport=({viewport_x:.1f}, {viewport_y:.1f})"
    )

    for event_type in ("mousePressed", "mouseReleased"):
        sb.cdp.loop.run_until_complete(
            sb.cdp.page.send(
                cdp_input.dispatch_mouse_event(
                    type_=event_type,
                    x=viewport_x,
                    y=viewport_y,
                    button=cdp_input.MouseButton.LEFT,
                    click_count=1,
                )
            )
        )


def main():
    print(f"Starting local viewer at http://localhost:{PORT}")
    threading.Thread(target=run_server, daemon=True).start()

    # headless=False deliberately - see the debugging notes at the top of
    # this file for why headless=True isn't worth testing here.
    with SB(uc=True, headless=False) as sb:
        sb.activate_cdp_mode(TARGET_URL)

        # Test-only sizing - see the Sizing note in the module docstring
        # for why this isn't the production answer.
        sb.cdp.loop.run_until_complete(
            sb.cdp.page.set_window_size(width=520, height=760)
        )

        sb.cdp.add_handler(cdp_page.ScreencastFrame, on_frame)
        sb.cdp.loop.run_until_complete(
            sb.cdp.page.send(
                cdp_page.start_screencast(
                    format_="jpeg",
                    quality=85,
                    max_width=900,
                    max_height=650,
                    every_nth_frame=1,
                )
            )
        )

        # Seed frame: startScreencast only pushes on repaint, so without
        # this the modal stays blank until the first real interaction.
        # No metadata comes with it, so clicks stay disabled (see
        # _dispatch_click) until the first real ScreencastFrame arrives.
        global _latest_frame
        first_frame = sb.cdp.loop.run_until_complete(
            sb.cdp.page.send(cdp_page.capture_screenshot(format_="jpeg", quality=70))
        )
        with _lock:
            _latest_frame = base64.b64decode(first_frame)

        with open("seed_frame.jpg", "wb") as f:
            f.write(_latest_frame)

        print(f"Screencast started, streaming {TARGET_URL}")
        print(f"Open http://localhost:{PORT} in a normal browser tab now.")
        print("Click 'Simulate: CAPTCHA required' to open the modal, then")
        print("click directly on the challenge inside the modal image -")
        print("clicks are forwarded into the REAL browser window. Watch")
        print("that real window to judge whether clicks land correctly.")
        print("Press Ctrl+C here ONCE when you're done.")

        last_print = time.time()
        try:
            while True:
                # 0.1s, not 1s: this loop is also what drains and
                # dispatches pending clicks now, so it needs to stay
                # responsive rather than only pumping once a second.
                sb.cdp.loop.run_until_complete(asyncio.sleep(0.1))

                while not _pending_clicks.empty():
                    frac_x, frac_y = _pending_clicks.get_nowait()
                    _dispatch_click(sb, frac_x, frac_y)

                if time.time() - last_print >= 1:
                    with _lock:
                        count = _frame_count
                    print(f"\rFrames received so far: {count}", end="", flush=True)
                    last_print = time.time()
        except KeyboardInterrupt:
            print("\nStopping...")
            # os._exit(), not return: `with SB(...)`'s own __exit__ runs
            # tearDown() -> _reconnect_if_disconnected() no matter how we
            # leave this block, and THAT is what was actually hanging
            # under --uc + manual CDP usage in earlier testing. Skipping
            # process teardown entirely is fine here - throwaway test
            # process, not something needing graceful app-level cleanup.
            os._exit(0)


if __name__ == "__main__":
    main()
