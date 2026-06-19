from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from bookmarks_organizer.models import CollectionRecord, TweetRecord


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.astimezone(timezone.utc).isoformat()


def _from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tweets (
                    tweet_id TEXT PRIMARY KEY,
                    author TEXT NOT NULL,
                    handle TEXT NOT NULL,
                    text TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    created_at TEXT,
                    bookmarked_at TEXT,
                    category TEXT NOT NULL DEFAULT 'General',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    inserted_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS embeddings (
                    tweet_id TEXT PRIMARY KEY REFERENCES tweets(tweet_id) ON DELETE CASCADE,
                    vector_json TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_state (
                    state_key TEXT PRIMARY KEY,
                    state_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS collections (
                    collection_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS collection_items (
                    collection_id INTEGER NOT NULL REFERENCES collections(collection_id) ON DELETE CASCADE,
                    tweet_id TEXT NOT NULL REFERENCES tweets(tweet_id) ON DELETE CASCADE,
                    added_at TEXT NOT NULL,
                    PRIMARY KEY (collection_id, tweet_id)
                )
                """
            )
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS bookmark_fts
                USING fts5(tweet_id UNINDEXED, author, handle, text, tags, category)
                """
            )

    def upsert_tweet(
        self,
        tweet: TweetRecord,
        metadata: dict[str, str] | None = None,
    ) -> None:
        timestamp = _to_iso(utcnow())
        metadata_payload: dict[str, object] = {
            "image_urls": tweet.image_urls,
            "video_urls": tweet.video_urls,
            "video_poster_urls": tweet.video_poster_urls,
        }
        if metadata:
            metadata_payload.update(metadata)
        payload = {
            "tweet_id": tweet.tweet_id,
            "author": tweet.author,
            "handle": tweet.handle,
            "text": tweet.text,
            "url": tweet.url,
            "created_at": _to_iso(tweet.created_at),
            "bookmarked_at": _to_iso(tweet.bookmarked_at),
            "category": tweet.category,
            "tags_json": json.dumps(tweet.tags),
            "metadata_json": json.dumps(metadata_payload),
            "inserted_at": timestamp,
            "updated_at": timestamp,
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO tweets (
                    tweet_id, author, handle, text, url, created_at, bookmarked_at,
                    category, tags_json, metadata_json, inserted_at, updated_at
                ) VALUES (
                    :tweet_id, :author, :handle, :text, :url, :created_at, :bookmarked_at,
                    :category, :tags_json, :metadata_json, :inserted_at, :updated_at
                )
                ON CONFLICT(tweet_id) DO UPDATE SET
                    author = excluded.author,
                    handle = excluded.handle,
                    text = excluded.text,
                    url = excluded.url,
                    created_at = excluded.created_at,
                    bookmarked_at = excluded.bookmarked_at,
                    category = excluded.category,
                    tags_json = excluded.tags_json,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                payload,
            )
            conn.execute("DELETE FROM bookmark_fts WHERE tweet_id = ?", (tweet.tweet_id,))
            conn.execute(
                """
                INSERT INTO bookmark_fts (tweet_id, author, handle, text, tags, category)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    tweet.tweet_id,
                    tweet.author,
                    tweet.handle,
                    tweet.text,
                    " ".join(tweet.tags),
                    tweet.category,
                ),
            )

    def upsert_embedding(self, tweet_id: str, vector: list[float], model_name: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO embeddings (tweet_id, vector_json, model_name, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tweet_id) DO UPDATE SET
                    vector_json = excluded.vector_json,
                    model_name = excluded.model_name,
                    updated_at = excluded.updated_at
                """,
                (tweet_id, json.dumps(vector), model_name, _to_iso(utcnow())),
            )

    def tweet_exists(self, tweet_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM tweets WHERE tweet_id = ? LIMIT 1",
                (tweet_id,),
            ).fetchone()
            return row is not None

    def get_tweet(self, tweet_id: str) -> TweetRecord | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM tweets WHERE tweet_id = ?", (tweet_id,)).fetchone()
            if row is None:
                return None
            return self._row_to_tweet(row)

    def list_recent_bookmarks(self, limit: int = 25) -> list[TweetRecord]:
        return self.list_bookmarks(limit=limit, sort="newest")

    def list_bookmarks(
        self,
        *,
        limit: int = 25,
        offset: int = 0,
        category: str | None = None,
        media: str = "all",
        sort: str = "newest",
    ) -> list[TweetRecord]:
        where_clause, params = self._build_bookmark_filters(category=category, media=media)
        order_clause = self._build_sort_clause(sort)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM tweets
                {where_clause}
                ORDER BY {order_clause}
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            ).fetchall()
            return [self._row_to_tweet(row) for row in rows]

    def count_bookmarks(
        self,
        *,
        category: str | None = None,
        media: str = "all",
    ) -> int:
        where_clause, params = self._build_bookmark_filters(category=category, media=media)
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) AS count FROM tweets {where_clause}",
                params,
            ).fetchone()
            return int(row["count"])

    def search_keyword(
        self,
        query: str,
        limit: int = 25,
        category: str | None = None,
        collection_id: int | None = None,
        media: str = "all",
    ) -> list[tuple[TweetRecord, float]]:
        sql = """
            SELECT t.*, -bm25(bookmark_fts) AS score
            FROM bookmark_fts
            JOIN tweets t ON t.tweet_id = bookmark_fts.tweet_id
        """
        clauses: list[str] = ["bookmark_fts MATCH ?"]
        params: list[object] = [query]
        if category:
            clauses.append("t.category = ?")
            params.append(category)
        media_clause = self._build_media_clause("t", media)
        if media_clause:
            clauses.append(media_clause)
        if collection_id is not None:
            sql += " JOIN collection_items ci ON ci.tweet_id = t.tweet_id "
            clauses.append("ci.collection_id = ?")
            params.append(collection_id)
        sql += " WHERE " + " AND ".join(clauses) + " ORDER BY score DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [(self._row_to_tweet(row), float(row["score"])) for row in rows]

    def list_embeddings(self) -> list[tuple[str, list[float]]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT tweet_id, vector_json FROM embeddings").fetchall()
            return [(row["tweet_id"], json.loads(row["vector_json"])) for row in rows]

    def get_embedding(self, tweet_id: str) -> list[float] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT vector_json FROM embeddings WHERE tweet_id = ?",
                (tweet_id,),
            ).fetchone()
            if row is None:
                return None
            return json.loads(row["vector_json"])

    def set_sync_state(self, latest_bookmark_id: str | None, last_sync_time: datetime | None) -> None:
        entries = {
            "latest_bookmark_id": latest_bookmark_id or "",
            "last_sync_time": _to_iso(last_sync_time) or "",
        }
        with self.connect() as conn:
            for key, value in entries.items():
                conn.execute(
                    """
                    INSERT INTO sync_state (state_key, state_value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(state_key) DO UPDATE SET
                        state_value = excluded.state_value,
                        updated_at = excluded.updated_at
                    """,
                    (key, value, _to_iso(utcnow())),
                )

    def get_sync_state(self) -> dict[str, str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT state_key, state_value FROM sync_state").fetchall()
        return {row["state_key"]: row["state_value"] for row in rows}

    def get_dashboard_stats(self) -> dict[str, int | str | None]:
        with self.connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS count FROM tweets").fetchone()["count"]
            week = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM tweets
                WHERE datetime(bookmarked_at) >= datetime('now', '-7 days')
                """
            ).fetchone()["count"]
            category_count = conn.execute(
                "SELECT COUNT(DISTINCT category) AS count FROM tweets"
            ).fetchone()["count"]
        state = self.get_sync_state()
        return {
            "total_bookmarks": int(total),
            "new_this_week": int(week),
            "category_count": int(category_count),
            "last_sync_time": state.get("last_sync_time") or None,
        }

    def get_category_counts(self) -> list[tuple[str, int]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT category, COUNT(*) AS total
                FROM tweets
                GROUP BY category
                ORDER BY total DESC, category ASC
                """
            ).fetchall()
            return [(row["category"], int(row["total"])) for row in rows]

    def create_collection(self, name: str, description: str = "") -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO collections (name, description, created_at)
                VALUES (?, ?, ?)
                """,
                (name.strip(), description.strip(), _to_iso(utcnow())),
            )
            return int(cursor.lastrowid)

    def list_collections(self) -> list[CollectionRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM collections ORDER BY created_at DESC, name ASC"
            ).fetchall()
            return [
                CollectionRecord(
                    collection_id=int(row["collection_id"]),
                    name=row["name"],
                    description=row["description"],
                    created_at=_from_iso(row["created_at"]),
                )
                for row in rows
            ]

    def add_to_collection(self, collection_id: int, tweet_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO collection_items (collection_id, tweet_id, added_at)
                VALUES (?, ?, ?)
                """,
                (collection_id, tweet_id, _to_iso(utcnow())),
            )

    def get_bookmarks_for_collection(self, collection_id: int, limit: int = 50) -> list[TweetRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT t.*
                FROM collection_items ci
                JOIN tweets t ON t.tweet_id = ci.tweet_id
                WHERE ci.collection_id = ?
                ORDER BY ci.added_at DESC
                LIMIT ?
                """,
                (collection_id, limit),
            ).fetchall()
            return [self._row_to_tweet(row) for row in rows]

    def _build_bookmark_filters(
        self,
        *,
        category: str | None,
        media: str,
        table_alias: str | None = None,
    ) -> tuple[str, list[object]]:
        alias = f"{table_alias}." if table_alias else ""
        clauses: list[str] = []
        params: list[object] = []
        if category:
            clauses.append(f"{alias}category = ?")
            params.append(category)
        media_clause = self._build_media_clause(table_alias, media)
        if media_clause:
            clauses.append(media_clause)
        if not clauses:
            return "", params
        return "WHERE " + " AND ".join(clauses), params

    def _build_media_clause(self, table_alias: str | None, media: str) -> str:
        alias = f"{table_alias}." if table_alias else ""
        image_count = (
            f"json_array_length(COALESCE(json_extract({alias}metadata_json, '$.image_urls'), json('[]')))"
        )
        video_count = (
            f"json_array_length(COALESCE(json_extract({alias}metadata_json, '$.video_urls'), json('[]')))"
        )
        poster_count = (
            f"json_array_length(COALESCE(json_extract({alias}metadata_json, '$.video_poster_urls'), json('[]')))"
        )
        if media == "images":
            return f"{image_count} > 0"
        if media == "video":
            return f"({video_count} > 0 OR {poster_count} > 0)"
        if media == "text":
            return f"({image_count} = 0 AND {video_count} = 0 AND {poster_count} = 0)"
        return ""

    def _build_sort_clause(self, sort: str) -> str:
        if sort == "oldest":
            return "COALESCE(bookmarked_at, inserted_at) ASC, created_at ASC"
        if sort == "author":
            return "LOWER(author) ASC, COALESCE(bookmarked_at, inserted_at) DESC"
        return "COALESCE(bookmarked_at, inserted_at) DESC, created_at DESC"

    def _row_to_tweet(self, row: sqlite3.Row) -> TweetRecord:
        metadata = json.loads(row["metadata_json"])
        return TweetRecord(
            tweet_id=row["tweet_id"],
            author=row["author"],
            handle=row["handle"],
            text=row["text"],
            url=row["url"],
            created_at=_from_iso(row["created_at"]),
            bookmarked_at=_from_iso(row["bookmarked_at"]),
            category=row["category"],
            tags=json.loads(row["tags_json"]),
            image_urls=list(metadata.get("image_urls", [])),
            video_urls=list(metadata.get("video_urls", [])),
            video_poster_urls=list(metadata.get("video_poster_urls", [])),
        )
