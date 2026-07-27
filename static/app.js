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

  const body = document.getElementById("formats-body");
  body.innerHTML = "";
  (data.formats || []).forEach((f) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${f.resolution}</td>
      <td>${f.ext}</td>
      <td>${f.has_audio ? "included" : "video only"}</td>
      <td>${f.filesize_display}</td>
    `;
    body.appendChild(row);
  });

  resultEl.hidden = false;
}
