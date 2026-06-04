from __future__ import annotations

from datetime import datetime, timezone

from bookmarks_organizer.db import Database
from bookmarks_organizer.models import TweetRecord


def test_database_upserts_and_searches(tmp_path) -> None:
    db = Database(tmp_path / "bookmarks.db")
    db.initialize()

    tweet = TweetRecord(
        tweet_id="42",
        author="Test Author",
        handle="@tester",
        text="Semantic search for AI agents and system design notes.",
        url="https://x.com/tester/status/42",
        created_at=datetime.now(timezone.utc),
        bookmarked_at=datetime.now(timezone.utc),
        category="AI",
        tags=["ai", "agents", "system-design"],
    )
    db.upsert_tweet(tweet)

    results = db.search_keyword("agents", limit=5)
    assert len(results) == 1
    stored, _ = results[0]
    assert stored.tweet_id == "42"
    assert db.tweet_exists("42") is True

