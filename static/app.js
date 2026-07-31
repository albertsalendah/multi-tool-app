const form = document.getElementById("info-form");
const errorEl = document.getElementById("error");
const resultEl = document.getElementById("result");
const btn = document.getElementById("fetch-btn");
const detectBtn = document.getElementById("detect-btn");

let lastUrl = "";
let activeSessionId = null;
let streamPollInterval = null;

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
      const res = await fetch("/api/v1/tools/video_downloader/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ params: { url } }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Could not fetch video info.");
      renderResult(data.result);
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.hidden = false;
    } finally {
      btn.disabled = false;
      btn.textContent = "Fetch details";
    }
  });
}

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
    detectBtn.textContent = "Browser opened... solve challenge if prompted";

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

async function startInteractiveSession(url) {
  const res = await fetch(`/tools/video-downloader/detect-interactive?url=${encodeURIComponent(url)}`, { method: "POST" });
  const session = await res.json();

  if (!res.ok) {
    throw new Error(session.detail || "Failed to launch detector.");
  }

  activeSessionId = session.session_id;

  streamPollInterval = setInterval(async () => {
    try {
      const statusRes = await fetch(`/tools/video-downloader/session/${activeSessionId}/status`);
      const data = await statusRes.json();

      if (data.status === "completed") {
        clearInterval(streamPollInterval);
        renderResult(data.result);
      } else if (data.status === "failed") {
        clearInterval(streamPollInterval);
        throw new Error(data.error || "Detection failed.");
      }
    } catch (err) {
      clearInterval(streamPollInterval);
      errorEl.textContent = err.message;
      errorEl.hidden = false;
    }
  }, 1000);
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