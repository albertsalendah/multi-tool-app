"""
CDP Screencast spike test - v2: mocked video_downloader.html page with
a modal-overlay reveal, matching how this would actually surface in
the real app.

Tests two things now: (1) does the live CDP screencast feel natural
(same as before), and (2) does showing it inside the app's real
modal-overlay UI (currently unused CSS in static/style.css) feel right
before any of this gets wired into the real backend.

Every screencast-related API used here (mycdp.page.start_screencast/
screencast_frame_ack/stop_screencast, the ScreencastFrame event's
.data/.session_id fields, sb.cdp.page.send() as the sanctioned way to
issue custom CDP commands, sb.cdp.add_handler() accepting a sync or
async callback, sb.activate_cdp_mode(url) accepting a URL directly)
was confirmed against the real installed seleniumbase + mycdp packages
before writing this, not assumed from memory.

Requires:
  pip install seleniumbase --break-system-packages
  style.css saved in the SAME folder as this script (copy of the real
  static/style.css from the repo - ask if you don't have it handy).

Run: python3 captcha_screencast_test.py [url]
Then open: http://localhost:8091 - you'll see a mock of the real
Video Downloader page. Click "Simulate: CAPTCHA required" to open the
modal and see the live stream inside it.

This still only tests the VIEWING side - no click-forwarding into the
real browser session yet.
"""

import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import mycdp.page as cdp_page
from seleniumbase import SB

PORT = 8091
TARGET_URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.google.com/recaptcha/api2/demo"
CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.css")

_lock = threading.Lock()
_latest_frame = None  # raw JPEG bytes of the most recent frame
_frame_count = 0


class StreamHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # quiet - don't spam the console per request

    def do_GET(self):
        if self.path == "/":
            self._serve_index()
        elif self.path == "/assets/style.css":
            self._serve_css()
        elif self.path == "/stream":
            self._serve_mjpeg()
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

    def _serve_index(self):
        # This is the real static/video_downloader.html markup, unmodified,
        # plus one test-only button and the modal overlay wired to the
        # live screencast - so the UI you're judging is the real one, not
        # an approximation of it. The modal reuses the existing (currently
        # unused in the real app) .modal-overlay/.canvas-wrapper/
        # .canvas-loader CSS classes from static/style.css directly - an
        # <img> tag turns out to slot into #stream-canvas's styling just
        # as well as the <canvas> it was originally built for, since
        # object-fit: contain works on both.
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
        <span class="modal-subtitle">Solve the challenge below to continue. This tab is watching a live feed of the real browser session.</span>
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

    document.getElementById('simulate-btn').addEventListener('click', () => {
      modal.hidden = false;
      loader.hidden = false;
      streamImg.src = '/stream';
    });

    streamImg.addEventListener('load', () => {
      loader.hidden = true;
    });

    document.getElementById('cancel-btn').addEventListener('click', () => {
      modal.hidden = true;
      streamImg.src = '';  // stop pulling the MJPEG stream
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

    def _serve_mjpeg(self):
        self.send_response(200)
        self.send_header(
            "Content-Type", "multipart/x-mixed-replace; boundary=frame"
        )
        self.end_headers()
        last_sent = None
        try:
            while True:
                with _lock:
                    frame = _latest_frame
                if frame is not None and frame is not last_sent:
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                    last_sent = frame
                time.sleep(0.03)  # ~33fps poll of the shared frame buffer
        except (BrokenPipeError, ConnectionResetError):
            pass  # viewer closed the tab


def run_server():
    server = ThreadingHTTPServer(("localhost", PORT), StreamHandler)
    server.serve_forever()


async def on_frame(event, connection):
    """CDP event handler - fires once per screencast frame. Confirmed
    against the real ScreencastFrame dataclass: .data is base64 JPEG,
    .session_id must be echoed back in the ack or Chrome stalls the
    stream waiting for acknowledgement."""
    global _latest_frame, _frame_count
    import base64

    with _lock:
        _latest_frame = base64.b64decode(event.data)
        _frame_count += 1

    await connection.send(cdp_page.screencast_frame_ack(session_id=event.session_id))


def main():
    print(f"Starting local viewer at http://localhost:{PORT}")
    threading.Thread(target=run_server, daemon=True).start()

    with SB(uc=True) as sb:
        sb.activate_cdp_mode(TARGET_URL)

        sb.cdp.add_handler(cdp_page.ScreencastFrame, on_frame)
        sb.cdp.loop.run_until_complete(
            sb.cdp.page.send(
                cdp_page.start_screencast(
                    format_="jpeg",
                    quality=70,
                    max_width=900,
                    max_height=650,
                    every_nth_frame=1,
                )
            )
        )

        print(f"Screencast started, streaming {TARGET_URL}")
        print(f"Open http://localhost:{PORT} in a normal browser tab now.")
        print("Click 'Simulate: CAPTCHA required' to open the modal overlay")
        print("and see the live stream inside it - that's the part worth")
        print("judging now, not just the raw stream from before.")
        print("Interact with the REAL browser window SeleniumBase opened")
        print("(solve the captcha, trigger a puzzle, etc.) and watch the")
        print("modal in the mock tab to judge how it feels.")
        print("Press Ctrl+C here when you're done.")

        try:
            while True:
                time.sleep(1)
                with _lock:
                    count = _frame_count
                print(f"\rFrames received so far: {count}", end="", flush=True)
        except KeyboardInterrupt:
            print("\nStopping...")

        sb.cdp.loop.run_until_complete(
            sb.cdp.page.send(cdp_page.stop_screencast())
        )


if __name__ == "__main__":
    main()
