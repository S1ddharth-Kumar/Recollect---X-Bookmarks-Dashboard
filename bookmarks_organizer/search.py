from __future__ import annotations

from bookmarks_organizer.categorization import categorize_text, extract_tags
from bookmarks_organizer.db import Database
from bookmarks_organizer.embeddings import EmbeddingProvider, clean_text
from bookmarks_organizer.models import SearchResult, TweetRecord
from bookmarks_organizer.vector_store import SemanticIndex


class SearchService:
    def __init__(
        self,
        db: Database,
        embedding_provider: EmbeddingProvider,
        semantic_index: SemanticIndex,
    ) -> None:
        self.db = db
        self.embedding_provider = embedding_provider
        self.semantic_index = semantic_index

    def enrich_and_index(self, tweet: TweetRecord) -> TweetRecord:
        cleaned = clean_text(tweet.text)
        tweet.category = categorize_text(cleaned)
        tweet.tags = extract_tags(cleaned, tweet.category)
        self.db.upsert_tweet(tweet)
        vector = self.embedding_provider.encode(f"{tweet.author} {tweet.text}")
        self.db.upsert_embedding(tweet.tweet_id, vector, self.embedding_provider.model_name)
        self.semantic_index.mark_dirty()
        return tweet

    def find_similar(self, tweet_id: str, limit: int = 5) -> list[SearchResult]:
        tweet = self.db.get_tweet(tweet_id)
        if tweet is None:
            return []
        vector = self.db.get_embedding(tweet_id)
        if vector is None:
            vector = self.embedding_provider.encode(f"{tweet.author} {tweet.text}")
        results = self.semantic_index.search(vector, limit=limit + 1)
        similar: list[SearchResult] = []
        for result_tweet_id, score in results:
            if result_tweet_id == tweet_id:
                continue
            related = self.db.get_tweet(result_tweet_id)
            if related is None:
                continue
            similar.append(SearchResult(tweet=related, score=score, source="semantic"))
            if len(similar) >= limit:
                break
        return similar

    def search(
        self,
        query: str,
        *,
        mode: str = "hybrid",
        limit: int = 20,
        category: str | None = None,
        collection_id: int | None = None,
        media: str = "all",
        sort: str = "relevance",
    ) -> list[SearchResult]:
        normalized_query = query.strip()
        if not normalized_query:
            return [
                SearchResult(tweet=tweet, score=1.0, source="recent")
                for tweet in self.db.list_bookmarks(
                    limit=limit,
                    category=category,
                    media=media,
                    sort="newest" if sort == "relevance" else sort,
                )
            ]

        keyword_results: dict[str, SearchResult] = {}
        if mode in {"keyword", "hybrid"}:
            for tweet, score in self.db.search_keyword(
                normalized_query,
                limit=limit * 3,
                category=category,
                collection_id=collection_id,
                media=media,
            ):
                keyword_results[tweet.tweet_id] = SearchResult(tweet=tweet, score=score, source="keyword")

        semantic_results: dict[str, SearchResult] = {}
        if mode in {"semantic", "hybrid"}:
            query_vector = self.embedding_provider.encode(normalized_query)
            for tweet_id, score in self.semantic_index.search(query_vector, limit=limit * 5):
                tweet = self.db.get_tweet(tweet_id)
                if tweet is None:
                    continue
                if category and tweet.category != category:
                    continue
                if not self._matches_media(tweet, media):
                    continue
                semantic_results[tweet_id] = SearchResult(tweet=tweet, score=score, source="semantic")

        if mode == "keyword":
            results = list(keyword_results.values())
            return self._sort_results(results, sort)[:limit]
        if mode == "semantic":
            results = sorted(semantic_results.values(), key=lambda item: item.score, reverse=True)
            return self._sort_results(results, sort)[:limit]

        combined: dict[str, SearchResult] = {}
        for tweet_id, result in semantic_results.items():
            combined[tweet_id] = SearchResult(tweet=result.tweet, score=result.score * 0.65, source="semantic")
        for tweet_id, result in keyword_results.items():
            existing = combined.get(tweet_id)
            if existing is None:
                combined[tweet_id] = SearchResult(
                    tweet=result.tweet,
                    score=result.score * 0.35,
                    source="keyword",
                )
                continue
            existing.score += result.score * 0.35
            existing.source = "hybrid"
        ranked = sorted(combined.values(), key=lambda item: item.score, reverse=True)
        return self._sort_results(ranked, sort)[:limit]

    def _matches_media(self, tweet: TweetRecord, media: str) -> bool:
        has_images = bool(tweet.image_urls)
        has_video = bool(tweet.video_urls or tweet.video_poster_urls)
        if media == "images":
            return has_images
        if media == "video":
            return has_video
        if media == "text":
            return not has_images and not has_video
        return True

    def _sort_results(self, results: list[SearchResult], sort: str) -> list[SearchResult]:
        def sort_timestamp(item: SearchResult) -> float:
            value = item.tweet.bookmarked_at or item.tweet.created_at
            return value.timestamp() if value is not None else 0.0

        if sort == "oldest":
            return sorted(results, key=sort_timestamp)
        if sort == "author":
            return sorted(
                results,
                key=lambda item: (
                    item.tweet.author.lower(),
                    -sort_timestamp(item),
                ),
            )
        if sort == "newest":
            return sorted(results, key=sort_timestamp, reverse=True)
        return results
