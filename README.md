# Twitter/X Bookmarks Organizer

A local-first MVP for turning Twitter/X bookmarks into a searchable personal knowledge base.

## What it includes

- Incremental bookmark sync with Playwright and a persistent browser profile
- SQLite storage with FTS5 keyword search
- Semantic search with a resilient fallback pipeline
- Auto-categorization and tag extraction
- FastAPI + Jinja + HTMX dashboard and search UI
- Weekly scheduling plus a manual sync action
- Manual bookmark import from your regular browser session

## Why `uv`

This project is set up for `uv` instead of `pip` so dependency resolution is cleaner and easier to recover when Python packages shift across versions or compliance requirements.

## Quick start

```powershell
uv sync --group dev
uv run playwright install chromium
uv run python scripts/seed_demo.py
uv run uvicorn bookmarks_organizer.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Optional semantic stack

The app works out of the box with a deterministic local hashing embedder.

If you want transformer embeddings:

```powershell
uv sync --group dev --extra semantic
```

On Windows, FAISS may not be available for your Python version. The app automatically falls back to an in-process cosine-similarity index when that happens.

## Running a real sync

```powershell
uv run python scripts/sync_once.py
```

The sync service uses a persistent browser profile under `data/browser-profile`. On the first run, sign in to X in the Playwright window if needed, then let the sync continue.

## Manual import without Playwright

If browser automation keeps failing, use your normal logged-in browser instead.

1. Open `https://x.com/i/bookmarks`
2. Scroll until the bookmarks you want are visible
3. Paste the snippet from [scripts/export_bookmarks_console.js](C:/Users/salti/OneDrive/Documents/bookmarks-project/scripts/export_bookmarks_console.js) into the browser DevTools console
4. The export includes tweet text plus any visible images and video previews that are present in the page DOM
5. Upload the downloaded JSON from the dashboard, or import it from the CLI:

```powershell
uv run python scripts/import_bookmarks.py path\to\x-bookmarks-export.json
```

## Project layout

- `bookmarks_organizer/` application package
- `templates/` server-rendered UI
- `static/` CSS
- `scripts/` seed and sync helpers
- `tests/` unit tests
