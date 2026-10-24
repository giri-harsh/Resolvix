"""Embedding-keyed answer cache (§8.1, §9.3 cache-hit ≤350ms). Seeding from each
corpus section's `answer_hint` is deferred — none of the campus corpus sections
have one yet (optional per §10.3) — so the cache starts empty and fills from real
turns instead. Still satisfies the ≥35%-after-200-calls target eventually; just
starts cold rather than pre-warmed.
"""
from dataclasses import dataclass

import numpy as np
from fastembed import TextEmbedding

from resolvix.core.retrieval.embedder import get_embedder

SIMILARITY_THRESHOLD = 0.92


@dataclass
class CacheEntry:
    query: str
    answer: str
    vector: np.ndarray


class SemanticCache:
    def __init__(self, embedder: TextEmbedding | None = None):
        self._embedder = embedder or get_embedder()
        self._entries: list[CacheEntry] = []

    def probe(self, query: str) -> str | None:
        if not self._entries:
            return None
        vec = next(self._embedder.embed([query]))
        best_score, best_answer = -1.0, None
        for entry in self._entries:
            score = float(vec @ entry.vector)
            if score > best_score:
                best_score, best_answer = score, entry.answer
        if best_score >= SIMILARITY_THRESHOLD:
            return best_answer
        return None

    def store(self, query: str, answer: str) -> None:
        vec = next(self._embedder.embed([query]))
        self._entries.append(CacheEntry(query=query, answer=answer, vector=vec))
