from __future__ import annotations

import math
import re
from hashlib import blake2b
from typing import Protocol


def clean_text(text: str) -> str:
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


class EmbeddingProvider(Protocol):
    model_name: str
    dimension: int

    def encode(self, text: str) -> list[float]:
        ...


class HashingEmbeddingProvider:
    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension
        self.model_name = f"hashing-local-{dimension}"

    def encode(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in re.findall(r"[a-zA-Z0-9_+#.-]{2,}", clean_text(text).lower()):
            digest = blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest, byteorder="big") % self.dimension
            vector[index] += 1.0
        return l2_normalize(vector)


class SentenceTransformerEmbeddingProvider:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self._model = SentenceTransformer(model_name)
        sample = self._model.encode(["dimension probe"], normalize_embeddings=True)
        self.dimension = len(sample[0])

    def encode(self, text: str) -> list[float]:
        result = self._model.encode([clean_text(text)], normalize_embeddings=True)
        return [float(value) for value in result[0]]


def build_embedding_provider(model_name: str, fallback_dimension: int) -> EmbeddingProvider:
    try:
        return SentenceTransformerEmbeddingProvider(model_name=model_name)
    except Exception:
        return HashingEmbeddingProvider(dimension=fallback_dimension)
