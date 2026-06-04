from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class TweetRecord:
    tweet_id: str
    author: str
    handle: str
    text: str
    url: str
    created_at: datetime | None = None
    bookmarked_at: datetime | None = None
    category: str = "General"
    tags: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    video_urls: list[str] = field(default_factory=list)
    video_poster_urls: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SearchResult:
    tweet: TweetRecord
    score: float
    source: str


@dataclass(slots=True)
class SyncSummary:
    added_count: int
    stopped_on_existing: bool
    latest_bookmark_id: str | None
    synced_at: datetime


@dataclass(slots=True)
class CollectionRecord:
    collection_id: int
    name: str
    description: str
    created_at: datetime | None = None


@dataclass(slots=True)
class ImportSummary:
    imported_count: int
    new_count: int
    updated_count: int
    latest_bookmark_id: str | None
    imported_at: datetime
