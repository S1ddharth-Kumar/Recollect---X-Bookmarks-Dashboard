from __future__ import annotations

import math
from threading import RLock

from bookmarks_organizer.db import Database


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


class SemanticIndex:
    def __init__(self, db: Database, prefer_faiss: bool = True) -> None:
        self.db = db
        self.prefer_faiss = prefer_faiss
        self._lock = RLock()
        self._tweet_ids: list[str] = []
        self._vectors: list[list[float]] = []
        self._dirty = True
        self._faiss = None
        self._numpy = None
        self._faiss_index = None

    def mark_dirty(self) -> None:
        with self._lock:
            self._dirty = True

    def _load(self) -> None:
        with self._lock:
            if not self._dirty:
                return
            rows = self.db.list_embeddings()
            self._tweet_ids = [tweet_id for tweet_id, _ in rows]
            self._vectors = [vector for _, vector in rows]
            self._build_faiss()
            self._dirty = False

    def _build_faiss(self) -> None:
        self._faiss = None
        self._numpy = None
        self._faiss_index = None
        if not self.prefer_faiss or not self._vectors:
            return
        try:
            import faiss
            import numpy

            array = numpy.array(self._vectors, dtype="float32")
            index = faiss.IndexFlatIP(array.shape[1])
            index.add(array)
            self._faiss = faiss
            self._numpy = numpy
            self._faiss_index = index
        except Exception:
            self._faiss = None
            self._numpy = None
            self._faiss_index = None

    def search(self, query_vector: list[float], limit: int = 20) -> list[tuple[str, float]]:
        self._load()
        if not self._tweet_ids:
            return []
        if self._faiss_index is not None and self._numpy is not None:
            query = self._numpy.array([query_vector], dtype="float32")
            scores, indices = self._faiss_index.search(query, min(limit, len(self._tweet_ids)))
            results: list[tuple[str, float]] = []
            for score, index in zip(scores[0], indices[0], strict=False):
                if index == -1:
                    continue
                results.append((self._tweet_ids[int(index)], float(score)))
            return results
        scored = [
            (tweet_id, cosine_similarity(query_vector, vector))
            for tweet_id, vector in zip(self._tweet_ids, self._vectors, strict=False)
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]

