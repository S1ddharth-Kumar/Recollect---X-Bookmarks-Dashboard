# Recollect

A local-first dashboard for exploring, searching and organising your X (Twitter) bookmarks.

---

## Features

- **Dark minimal UI** — clean dark background with floating pill navigation and large serif type
- **Polaroid bookmark cards** — each bookmark displayed as a light-theme card with author, text, tags and media
- **Hybrid search** — combines full-text SQLite (FTS5) with local cosine-similarity embeddings for relevant results
- **Incremental sync** — automated bookmark harvesting via Playwright with a persistent local browser profile
- **Auto-categorisation** — keywords and categories are extracted and applied automatically on import
- **Custom collections** — group bookmarks into named collections for quick access

---

## Quick Start

Ensure you have [`uv`](https://github.com/astral-sh/uv) installed.

### 1. Install dependencies
```powershell
uv sync --group dev
```

### 2. Install Playwright
```powershell
uv run playwright install chromium
```

### 3. Seed demo data (optional)
```powershell
uv run python scripts/seed_demo.py
```

### 4. Start the server
```powershell
uv run uvicorn bookmarks_organizer.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

---

## Syncing Your Bookmarks

```powershell
uv run python scripts/sync_once.py
```

A Playwright browser window will open. Log in to X on the first run — subsequent runs will fetch bookmarks incrementally.

---

## Project Structure

```
├── bookmarks_organizer/   # FastAPI app, database, search & sync logic
│   ├── config.py          # App settings
│   ├── db.py              # SQLite schema and query layer
│   ├── search.py          # Hybrid + semantic search service
│   └── sync_service.py    # Playwright-based bookmark sync
├── templates/             # Jinja2 HTML templates
│   ├── base.html          # Shared layout with pill nav
│   ├── dashboard.html     # Home page with hero and recent bookmarks
│   ├── search.html        # Full search and filter page
│   └── partials/          # Reusable card and list components
├── static/
│   └── style.css          # Design system CSS
├── scripts/               # CLI utilities and manual import helpers
└── tests/                 # Test suite
```

---

## License

MIT
