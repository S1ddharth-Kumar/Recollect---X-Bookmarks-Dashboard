from __future__ import annotations

import asyncio

from bookmarks_organizer.config import get_settings
from bookmarks_organizer.db import Database
from bookmarks_organizer.embeddings import build_embedding_provider
from bookmarks_organizer.search import SearchService
from bookmarks_organizer.sync_service import BookmarkSyncService
from bookmarks_organizer.vector_store import SemanticIndex


async def _run() -> None:
    settings = get_settings()
    db = Database(settings.database_path)
    db.initialize()
    provider = build_embedding_provider(settings.embedding_model, settings.embedding_dimension)
    search_service = SearchService(db, provider, SemanticIndex(db, prefer_faiss=settings.use_faiss))
    sync_service = BookmarkSyncService(
        db=db,
        search_service=search_service,
        browser_profile_dir=str(settings.browser_profile_dir),
        headless=settings.sync_headless,
        max_scrolls=settings.max_sync_scrolls,
        max_batch=settings.max_sync_batch,
        login_wait_seconds=settings.login_wait_seconds,
    )
    summary = await sync_service.sync_new_bookmarks()
    print(
        f"Added {summary.added_count} bookmark(s); "
        f"stopped_on_existing={summary.stopped_on_existing}; "
        f"latest={summary.latest_bookmark_id}"
    )


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()

