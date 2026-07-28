const form = document.getElementById("info-form");
const errorEl = document.getElementById("error");
const resultEl = document.getElementById("result");
const btn = document.getElementById("fetch-btn");
const detectBtn = document.getElementById("detect-btn");

let lastUrl = "";
let activeSessionId = null;
let streamPollInterval = null;

const modal = document.getElementById("turnstile-modal");
const streamCanvas = document.getElementById("stream-canvas");
const canvasLoader = document.getElementById("canvas-loader");

if (detectBtn) {
  detectBtn.hidden = false;
}

if (form) {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const urlInput = document.getElementById("url");
    const url = urlInput ? urlInput.value.trim() : "";
    if (!url) return;

    lastUrl = url;
    errorEl.hidden = true;
    resultEl.hidden = true;
    btn.disabled = true;
    btn.textContent = "Fetching...";

    try {
      const res = await fetch(`/tools/video-downloader/info?url=${encodeURIComponent(url)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Could not fetch video info.");
      renderResult(data);
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.hidden = false;
    } finally {
      btn.disabled = false;
      btn.textContent = "Fetch details";
    }
  });
}

// Single handler for generic detection modal
if (detectBtn) {
  detectBtn.addEventListener("click", async () => {
    const urlInput = document.getElementById("url");
    const url = (urlInput ? urlInput.value.trim() : "") || lastUrl;

    if (!url) {
      errorEl.textContent = "Please enter a valid video or page URL first.";
      errorEl.hidden = false;
      return;
    }

    errorEl.hidden = true;
    detectBtn.disabled = true;
    detectBtn.textContent = "Detecting... (interactive session)";

    try {
      await startInteractiveSession(url);
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.hidden = false;
    } finally {
      detectBtn.disabled = false;
      detectBtn.textContent = "Try generic detection (slower)";
    }
  });
}

// Canvas coordinate click handler
if (streamCanvas) {
  streamCanvas.addEventListener("click", async (e) => {
    if (!activeSessionId) return;

    const rect = streamCanvas.getBoundingClientRect();
    const scaleX = streamCanvas.naturalWidth / rect.width;
    const scaleY = streamCanvas.naturalHeight / rect.height;

    const clickX = Math.round((e.clientX - rect.left) * scaleX);
    const clickY = Math.round((e.clientY - rect.top) * scaleY);

    if (canvasLoader) canvasLoader.hidden = false;

    try {
      await fetch(`/tools/video-downloader/session/${activeSessionId}/click`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ x: clickX, y: clickY }),
      });
    } catch (err) {
      console.error("Click dispatch error:", err);
    }
  });
}

async function startInteractiveSession(url) {
  modal.hidden = false;

  const res = await fetch(`/tools/video-downloader/detect-interactive?url=${encodeURIComponent(url)}`, { method: "POST" });
  const session = await res.json();

  if (!res.ok) {
    modal.hidden = true;
    throw new Error(session.detail || "Failed to launch detector.");
  }

  activeSessionId = session.session_id;

  streamPollInterval = setInterval(async () => {
  try {
    const statusRes = await fetch(`/tools/video-downloader/session/${activeSessionId}/status`);
    const data = await statusRes.json();

    // Fix: Only set src when base64 string actually contains image data!
    if (data.screenshot && data.screenshot.length > 0) {
      streamCanvas.src = `data:image/jpeg;base64,${data.screenshot}`;
    }

    if (canvasLoader) canvasLoader.hidden = true;

    if (data.status === "completed") {
      clearInterval(streamPollInterval);
      modal.hidden = true;
      renderResult(data.result);
    } else if (data.status === "failed") {
      clearInterval(streamPollInterval);
      modal.hidden = true;
      throw new Error(data.error || "Detection failed.");
    }
  } catch (err) {
    clearInterval(streamPollInterval);
    modal.hidden = true;
    errorEl.textContent = err.message;
    errorEl.hidden = false;
  }
}, 800);
}

let currentAudioFormats = [];

function humanSize(numBytes) {
  if (!numBytes) return "Unknown";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = numBytes;
  let i = 0;
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024;
    i++;
  }
  return `${size.toFixed(1)} ${units[i]}`;
}

function updateTotal(select) {
  const videoSizeAttr = select.dataset.videoSize;
  const videoSize = videoSizeAttr ? Number(videoSizeAttr) : null;
  const audio = select.value !== "" ? currentAudioFormats[select.value] : null;
  const audioSize = audio ? audio.filesize : null;

  const targetCell = document.getElementById(select.dataset.sizeTarget);
  if (videoSize == null && audioSize == null) {
    targetCell.textContent = "Unknown";
    return;
  }
  const total = (videoSize || 0) + (audioSize || 0);
  const partial = videoSize == null || audioSize == null;
  targetCell.textContent = humanSize(total) + (partial ? " (partial)" : "");
}

function renderResult(data) {
  document.getElementById("video-title").textContent = data.title || "Untitled";
  document.getElementById("video-meta").textContent =
    [data.duration_string, data.extractor].filter(Boolean).join(" \u00b7 ");

  const thumb = document.getElementById("thumb");
  if (thumb) {
    if (data.thumbnail) {
      thumb.src = data.thumbnail;
      thumb.hidden = false;
    } else {
      thumb.hidden = true;
    }
  }

  currentAudioFormats = data.audio_formats || [];

  const body = document.getElementById("formats-body");
  body.innerHTML = "";

  let formats = (data.formats && data.formats.length > 0) ? data.formats : [
    {
      resolution: "Auto / Best",
      ext: "mp4",
      has_audio: true,
      filesize_display: "Unknown"
    }
  ];

  formats.forEach((f, idx) => {
    const row = document.createElement("tr");
    const sizeCellId = `size-${idx}`;

    const resDisplay = f.resolution || f.format_note || "Standard";
    const extDisplay = f.ext || "mp4";
    const sizeDisplay = f.filesize_display || humanSize(f.filesize) || "Unknown";

    if (f.has_audio || !currentAudioFormats.length) {
      row.innerHTML = `
        <td>${resDisplay}</td>
        <td>${extDisplay}</td>
        <td>included</td>
        <td id="${sizeCellId}">${sizeDisplay}</td>
      `;
      body.appendChild(row);
      return;
    }

    const options = currentAudioFormats
      .map((a, ai) => `<option value="${ai}">${a.bitrate_display} \u00b7 ${a.ext}</option>`)
      .join("");

    row.innerHTML = `
      <td>${resDisplay}</td>
      <td>${extDisplay}</td>
      <td><select class="audio-select" data-video-size="${f.filesize ?? ""}" data-size-target="${sizeCellId}">${options}</select></td>
      <td id="${sizeCellId}"></td>
    `;
    body.appendChild(row);

    const select = row.querySelector(".audio-select");
    if (select) {
      select.addEventListener("change", () => updateTotal(select));
      updateTotal(select);
    }
  });

  resultEl.hidden = false;
}

// Poll extension-captured streams
async function pollCapturedStreams() {
  try {
    const res = await fetch('/tools/video-downloader/recent-streams');
    const streams = await res.json();

    let container = document.getElementById('captured-streams-banner');
    if (!container) {
      container = document.createElement('div');
      container.id = 'captured-streams-banner';
      container.style.cssText = 'margin: 1rem 0; padding: 1rem; background: #1e293b; border-radius: 8px; border: 1px solid #22c55e;';
      const formEl = document.querySelector('form') || document.body;
      formEl.prepend(container);
    }

    if (streams.length === 0) {
      container.style.display = 'none';
      return;
    }

    container.style.display = 'block';
    const latest = streams[streams.length - 1];

    container.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
          <strong style="color: #22c55e; font-size: 15px;">🎬 ${latest.page_title}</strong>
          <div style="font-size: 11px; color: #94a3b8; margin-top: 4px; word-break: break-all;">
            ${latest.stream_url}
          </div>
        </div>
        <button type="button" id="use-captured-btn" style="padding: 6px 12px; background: #22c55e; color: #000; font-weight: bold; border: none; border-radius: 4px; cursor: pointer; margin-left: 12px;">
          Use Link
        </button>
      </div>
    `;

    document.getElementById('use-captured-btn').onclick = () => {
      const input = document.querySelector('input[name="url"]') || document.querySelector('#url');
      if (input) {
        input.value = latest.stream_url;
      }
    };
  } catch (err) {
    console.error("Error polling streams:", err);
  }
}

setInterval(pollCapturedStreams, 2000);