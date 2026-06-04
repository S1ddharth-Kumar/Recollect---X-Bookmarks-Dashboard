# Quick Walkthrough

This is the fastest way to get the app running locally.

## 1. Open the project folder

```powershell
cd C:\Users\salti\OneDrive\Documents\bookmarks-project
```

## 2. Set a local `uv` cache for this repo

This avoids the cache-path issue that can happen on this machine.

```powershell
$env:UV_CACHE_DIR='C:\Users\salti\OneDrive\Documents\bookmarks-project\.uv-cache'
```

## 3. Install dependencies with `uv`

```powershell
uv sync --group dev
```

Optional semantic stack:

```powershell
uv sync --group dev --extra semantic
```

## 4. Seed demo bookmarks

This gives you sample data immediately so the UI is not empty.

```powershell
uv run python scripts/seed_demo.py
```

## 5. Start the app

```powershell
uv run uvicorn bookmarks_organizer.main:app --reload
```

Then open:

[http://127.0.0.1:8000](http://127.0.0.1:8000)

## 6. Optional: enable real X bookmark sync

Install the Playwright browser once:

```powershell
uv run playwright install chromium
```

Run a one-time sync:

```powershell
uv run python scripts/sync_once.py
```

Notes:

- The browser profile is stored in `data/browser-profile`.
- On first sync, sign in to X if Playwright opens a login screen.
- The app only adds new bookmarks and stops when it reaches an existing one.

## 7. Recommended fallback: manual import from your normal browser

If Playwright login keeps crashing, use this instead:

1. Open `https://x.com/i/bookmarks` in your regular browser where you are already signed in.
2. Scroll until the bookmarks you want are visible.
3. Open DevTools Console.
4. Paste the code from `scripts/export_bookmarks_console.js`.
5. Save the downloaded JSON file.
6. Upload it from the dashboard's `Manual import` panel.

Notes:

- Images in visible bookmarks are now imported and shown in the app.
- Videos are imported on a best-effort basis. If Brave exposes a playable source in the page, the app stores it. Otherwise the app stores the video preview/poster and links back to the tweet.

CLI alternative:

```powershell
uv run python scripts/import_bookmarks.py path\to\x-bookmarks-export.json
```

## Useful commands

Run tests:

```powershell
uv run pytest
```

Rebuild demo data if needed:

```powershell
uv run python scripts/seed_demo.py
```
