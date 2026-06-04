from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

from bookmarks_organizer.db import Database
from bookmarks_organizer.models import ImportSummary, TweetRecord
from bookmarks_organizer.search import SearchService


URL_PATTERN = re.compile(r"https?://(?:www\.)?(?:x|twitter)\.com/[^/\s]+/status/\d+")
STATUS_PATTERN = re.compile(r"/status/(\d+)")


@dataclass(slots=True)
class ParsedBookmark:
    tweet_id: str
    author: str
    handle: str
    text: str
    url: str
    created_at: datetime | None
    bookmarked_at: datetime | None
    image_urls: list[str]
    video_urls: list[str]
    video_poster_urls: list[str]


def _normalize_media_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = [value]
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        candidate = str(item).strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    return normalized


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    normalized = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def extract_tweet_id(url: str) -> str | None:
    match = STATUS_PATTERN.search(url)
    if not match:
        return None
    return match.group(1)


def normalize_handle(value: str | None) -> str:
    if not value:
        return "@unknown"
    handle = value.strip()
    if not handle:
        return "@unknown"
    if not handle.startswith("@"):
        handle = f"@{handle}"
    return handle


def _record_to_bookmark(record: dict[str, object]) -> ParsedBookmark | None:
    url = str(record.get("url") or record.get("tweet_url") or "").strip()
    if not url:
        return None
    tweet_id = extract_tweet_id(url)
    if not tweet_id:
        return None
    author = str(record.get("author") or record.get("display_name") or "Unknown").strip() or "Unknown"
    handle = normalize_handle(
        str(record.get("handle") or record.get("username") or record.get("screen_name") or "")
    )
    text = str(record.get("text") or record.get("full_text") or record.get("content") or "").strip()
    if not text:
        text = f"Imported bookmark from {url}"
    created_at = parse_datetime(str(record.get("createdAt") or record.get("created_at") or ""))
    bookmarked_at = parse_datetime(
        str(record.get("bookmarkedAt") or record.get("bookmarked_at") or record.get("imported_at") or "")
    )
    image_urls = _normalize_media_list(record.get("imageUrls") or record.get("image_urls"))
    video_urls = _normalize_media_list(record.get("videoUrls") or record.get("video_urls"))
    video_poster_urls = _normalize_media_list(
        record.get("videoPosterUrls") or record.get("video_poster_urls") or record.get("videoThumbnails")
    )
    return ParsedBookmark(
        tweet_id=tweet_id,
        author=author,
        handle=handle,
        text=text,
        url=url,
        created_at=created_at,
        bookmarked_at=bookmarked_at,
        image_urls=image_urls,
        video_urls=video_urls,
        video_poster_urls=video_poster_urls,
    )


def parse_json_payload(payload: str) -> list[ParsedBookmark]:
    parsed = json.loads(payload)
    if isinstance(parsed, dict):
        if isinstance(parsed.get("bookmarks"), list):
            records = parsed["bookmarks"]
        elif isinstance(parsed.get("items"), list):
            records = parsed["items"]
        else:
            raise ValueError("JSON import must contain a list or a 'bookmarks' field.")
    elif isinstance(parsed, list):
        records = parsed
    else:
        raise ValueError("JSON import must be an array of bookmarks.")

    bookmarks: list[ParsedBookmark] = []
    seen_ids: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        bookmark = _record_to_bookmark(record)
        if bookmark is None or bookmark.tweet_id in seen_ids:
            continue
        seen_ids.add(bookmark.tweet_id)
        bookmarks.append(bookmark)
    return bookmarks


def parse_csv_payload(payload: str) -> list[ParsedBookmark]:
    reader = csv.DictReader(StringIO(payload))
    bookmarks: list[ParsedBookmark] = []
    seen_ids: set[str] = set()
    for row in reader:
        bookmark = _record_to_bookmark(row)
        if bookmark is None or bookmark.tweet_id in seen_ids:
            continue
        seen_ids.add(bookmark.tweet_id)
        bookmarks.append(bookmark)
    return bookmarks


def parse_url_lines_payload(payload: str) -> list[ParsedBookmark]:
    bookmarks: list[ParsedBookmark] = []
    seen_ids: set[str] = set()
    for line in payload.splitlines():
        match = URL_PATTERN.search(line)
        if not match:
            continue
        url = match.group(0)
        tweet_id = extract_tweet_id(url)
        if not tweet_id or tweet_id in seen_ids:
            continue
        seen_ids.add(tweet_id)
        bookmarks.append(
            ParsedBookmark(
                tweet_id=tweet_id,
                author="Unknown",
                handle="@unknown",
                text=f"Imported bookmark from {url}",
                url=url,
                created_at=None,
                bookmarked_at=None,
                image_urls=[],
                video_urls=[],
                video_poster_urls=[],
            )
        )
    return bookmarks


def detect_and_parse_payload(payload: str, filename: str | None = None) -> list[ParsedBookmark]:
    stripped = payload.lstrip()
    lower_name = (filename or "").lower()
    if lower_name.endswith(".json") or stripped.startswith("[") or stripped.startswith("{"):
        return parse_json_payload(payload)
    if lower_name.endswith(".csv"):
        return parse_csv_payload(payload)
    return parse_url_lines_payload(payload)


class ManualImportService:
    def __init__(self, db: Database, search_service: SearchService) -> None:
        self.db = db
        self.search_service = search_service

    def import_payload(self, payload: str, filename: str | None = None) -> ImportSummary:
        bookmarks = detect_and_parse_payload(payload, filename=filename)
        if not bookmarks:
            raise ValueError(
                "No bookmarks were found in the file. Use JSON, CSV, or plain X status URLs."
            )
        return self._store_bookmarks(bookmarks)

    def import_file(self, path: Path) -> ImportSummary:
        payload = path.read_text(encoding="utf-8")
        return self.import_payload(payload, filename=path.name)

    def _store_bookmarks(self, bookmarks: list[ParsedBookmark]) -> ImportSummary:
        imported_at = datetime.now(timezone.utc)
        new_count = 0
        updated_count = 0
        latest_bookmark_id = bookmarks[0].tweet_id if bookmarks else None

        for bookmark in bookmarks:
            existed = self.db.tweet_exists(bookmark.tweet_id)
            tweet = TweetRecord(
                tweet_id=bookmark.tweet_id,
                author=bookmark.author,
                handle=bookmark.handle,
                text=bookmark.text,
                url=bookmark.url,
                created_at=bookmark.created_at,
                bookmarked_at=bookmark.bookmarked_at or imported_at,
                image_urls=bookmark.image_urls,
                video_urls=bookmark.video_urls,
                video_poster_urls=bookmark.video_poster_urls,
            )
            self.search_service.enrich_and_index(tweet)
            if existed:
                updated_count += 1
            else:
                new_count += 1

        self.db.set_sync_state(latest_bookmark_id=latest_bookmark_id, last_sync_time=imported_at)
        return ImportSummary(
            imported_count=len(bookmarks),
            new_count=new_count,
            updated_count=updated_count,
            latest_bookmark_id=latest_bookmark_id,
            imported_at=imported_at,
        )
