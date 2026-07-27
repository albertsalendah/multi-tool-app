# Multi-Tool App

Personal web app: download video/files from various sources and push them to
a cloud storage provider of choice. Storage and processing backends are
swappable by design — see `project_handover.md` context for the full
architecture plan (not included in this repo).

Currently implemented: the app shell (tool grid + routing) and the Video
Downloader tool's layout. No extraction or upload logic yet — that's next.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Visit http://127.0.0.1:8000

## Run with Docker

```bash
docker build -t multi-tool-app .
docker run -p 8000:8000 multi-tool-app
```

## Adding a new tool

1. Create `<tool_name>/router.py` with its own `APIRouter`.
2. `include_router()` it in `main.py`.
3. Add a card for it in `static/index.html` linking to its route.

No other file needs to change — this is the adapter-style pattern the
project is built around.
