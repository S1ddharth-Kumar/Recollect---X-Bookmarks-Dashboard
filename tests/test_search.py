from __future__ import annotations

from datetime import datetime, timezone

from bookmarks_organizer.db import Database
from bookmarks_organizer.embeddings import HashingEmbeddingProvider
from bookmarks_organizer.models import TweetRecord
from bookmarks_organizer.search import SearchService
from bookmarks_organizer.vector_store import SemanticIndex


def test_hybrid_search_returns_seeded_bookmark(tmp_path) -> None:
    db = Database(tmp_path / "bookmarks.db")
    db.initialize()
    service = SearchService(
        db=db,
        embedding_provider=HashingEmbeddingProvider(dimension=128),
        semantic_index=SemanticIndex(db, prefer_faiss=False),
    )
    tweet = TweetRecord(
        tweet_id="7",
        author="Alex",
        handle="@alex",
        text="Practical notes on personal knowledge bases and semantic retrieval.",
        url="https://x.com/alex/status/7",
        created_at=datetime.now(timezone.utc),
        bookmarked_at=datetime.now(timezone.utc),
    )
    service.enrich_and_index(tweet)

    results = service.search("semantic retrieval", mode="hybrid")
    assert results
    assert results[0].tweet.tweet_id == "7"
