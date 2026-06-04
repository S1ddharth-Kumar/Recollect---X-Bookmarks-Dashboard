from __future__ import annotations

import json

from bookmarks_organizer.db import Database
from bookmarks_organizer.embeddings import HashingEmbeddingProvider
from bookmarks_organizer.manual_import import ManualImportService, detect_and_parse_payload
from bookmarks_organizer.search import SearchService
from bookmarks_organizer.vector_store import SemanticIndex


def _build_import_service(tmp_path) -> ManualImportService:
    db = Database(tmp_path / "bookmarks.db")
    db.initialize()
    search_service = SearchService(
        db=db,
        embedding_provider=HashingEmbeddingProvider(dimension=128),
        semantic_index=SemanticIndex(db, prefer_faiss=False),
    )
    return ManualImportService(db=db, search_service=search_service)


def test_detect_and_parse_json_payload() -> None:
    payload = json.dumps(
        [
            {
                "url": "https://x.com/example/status/12345",
                "text": "Semantic search for bookmarks",
                "author": "Example",
                "handle": "@example",
                "createdAt": "2026-05-31T10:00:00Z",
                "imageUrls": ["https://pbs.twimg.com/media/demo.jpg?format=jpg&name=small"],
                "videoPosterUrls": ["https://pbs.twimg.com/ext_tw_video_thumb/demo.jpg?name=small"],
            }
        ]
    )
    bookmarks = detect_and_parse_payload(payload, filename="export.json")
    assert len(bookmarks) == 1
    assert bookmarks[0].tweet_id == "12345"
    assert len(bookmarks[0].image_urls) == 1
    assert len(bookmarks[0].video_poster_urls) == 1


def test_manual_import_adds_and_updates_bookmarks(tmp_path) -> None:
    service = _build_import_service(tmp_path)
    payload = json.dumps(
        [
            {
                "url": "https://x.com/example/status/12345",
                "text": "Semantic search for bookmarks",
                "author": "Example",
                "handle": "@example",
                "imageUrls": ["https://pbs.twimg.com/media/demo.jpg?format=jpg&name=large"],
            }
        ]
    )
    first = service.import_payload(payload, filename="export.json")
    second = service.import_payload(payload, filename="export.json")
    assert first.new_count == 1
    assert first.updated_count == 0
    assert second.new_count == 0
    assert second.updated_count == 1


def test_imported_media_is_stored_on_tweet(tmp_path) -> None:
    service = _build_import_service(tmp_path)
    payload = json.dumps(
        [
            {
                "url": "https://x.com/example/status/22222",
                "text": "Bookmark with media",
                "author": "Example",
                "handle": "@example",
                "imageUrls": ["https://pbs.twimg.com/media/demo2.jpg?format=jpg&name=large"],
                "videoUrls": ["https://video.twimg.com/ext_tw_video/demo.mp4"],
                "videoPosterUrls": ["https://pbs.twimg.com/ext_tw_video_thumb/demo2.jpg?name=large"],
            }
        ]
    )
    service.import_payload(payload, filename="export.json")
    stored = service.db.get_tweet("22222")
    assert stored is not None
    assert stored.image_urls
    assert stored.video_urls
    assert stored.video_poster_urls
