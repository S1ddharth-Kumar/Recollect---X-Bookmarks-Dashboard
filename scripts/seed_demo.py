from __future__ import annotations

from datetime import datetime, timedelta, timezone

from bookmarks_organizer.config import get_settings
from bookmarks_organizer.db import Database
from bookmarks_organizer.embeddings import build_embedding_provider
from bookmarks_organizer.models import TweetRecord
from bookmarks_organizer.search import SearchService
from bookmarks_organizer.vector_store import SemanticIndex


def main() -> None:
    settings = get_settings()
    db = Database(settings.database_path)
    db.initialize()
    provider = build_embedding_provider(settings.embedding_model, settings.embedding_dimension)
    search_service = SearchService(db, provider, SemanticIndex(db, prefer_faiss=settings.use_faiss))

    now = datetime.now(timezone.utc)
    samples = [
        TweetRecord(
            tweet_id="1001",
            author="Jane Builder",
            handle="@janebuilder",
            text="A practical guide to building AI agents with retrieval, tool use, and evaluation loops.",
            url="https://x.com/janebuilder/status/1001",
            created_at=now - timedelta(days=12),
            bookmarked_at=now - timedelta(days=4),
        ),
        TweetRecord(
            tweet_id="1002",
            author="Arun Systems",
            handle="@arunsystems",
            text="System design note: why SQLite plus append-only backups is underrated for single-user products.",
            url="https://x.com/arunsystems/status/1002",
            created_at=now - timedelta(days=9),
            bookmarked_at=now - timedelta(days=3),
        ),
        TweetRecord(
            tweet_id="1003",
            author="Mina Research",
            handle="@minaresearch",
            text="New paper on efficient embedding models for semantic search over personal knowledge bases.",
            url="https://x.com/minaresearch/status/1003",
            created_at=now - timedelta(days=7),
            bookmarked_at=now - timedelta(days=2),
        ),
        TweetRecord(
            tweet_id="1004",
            author="Sam Founder",
            handle="@samfounder",
            text="Startup lesson: your first power users care more about workflow compression than feature count.",
            url="https://x.com/samfounder/status/1004",
            created_at=now - timedelta(days=5),
            bookmarked_at=now - timedelta(days=1),
        ),
    ]

    for tweet in samples:
        search_service.enrich_and_index(tweet)

    db.set_sync_state(latest_bookmark_id=samples[-1].tweet_id, last_sync_time=now)
    print(f"Seeded {len(samples)} demo bookmarks into {settings.database_path}")


if __name__ == "__main__":
    main()

