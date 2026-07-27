const form = document.getElementById("info-form");
const errorEl = document.getElementById("error");
const resultEl = document.getElementById("result");
const btn = document.getElementById("fetch-btn");

if (form) {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const url = document.getElementById("url").value.trim();
    if (!url) return;

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
  if (data.thumbnail) {
    thumb.src = data.thumbnail;
    thumb.hidden = false;
  } else {
    thumb.hidden = true;
  }

  currentAudioFormats = data.audio_formats || [];

  const body = document.getElementById("formats-body");
  body.innerHTML = "";

  (data.formats || []).forEach((f, idx) => {
    const row = document.createElement("tr");
    const sizeCellId = `size-${idx}`;

    if (f.has_audio) {
      // Audio is already muxed into this file — nothing to pick or add.
      row.innerHTML = `
        <td>${f.resolution}</td>
        <td>${f.ext}</td>
        <td>included</td>
        <td id="${sizeCellId}">${f.filesize_display}</td>
      `;
      body.appendChild(row);
      return;
    }

    const options = currentAudioFormats.length
      ? currentAudioFormats
          .map((a, ai) => `<option value="${ai}">${a.bitrate_display} \u00b7 ${a.ext}</option>`)
          .join("")
      : `<option value="">no separate audio track found</option>`;

    row.innerHTML = `
      <td>${f.resolution}</td>
      <td>${f.ext}</td>
      <td><select class="audio-select" data-video-size="${f.filesize ?? ""}" data-size-target="${sizeCellId}">${options}</select></td>
      <td id="${sizeCellId}"></td>
    `;
    body.appendChild(row);

    // Defaults to the first (best-bitrate) audio option; user can change it.
    const select = row.querySelector(".audio-select");
    select.addEventListener("change", () => updateTotal(select));
    updateTotal(select);
  });

  resultEl.hidden = false;
}
