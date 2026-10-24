"""Hybrid BM25 + dense retrieval with Reciprocal Rank Fusion (§8.1, §9.2 5b).

Built in-memory at process startup rather than from a prebuilt `corpus.index.npz`
artifact (PRD's `make build-index` step) — the corpus is ~70 chunks, so an on-disk
index + lock-hash mismatch guard buys nothing at this scale and adds a build step
with no latency payoff. Revisit if the corpus grows enough that embedding at boot
becomes the slow part.
"""
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

from resolvix.core.retrieval.chunking import Chunk, load_corpus
from resolvix.core.retrieval.embedder import get_embedder

# Reconstructed suffix stemmer (v1's exact 9-suffix list was lost with rag.py's
# deletion, not ported verbatim) — same purpose: fold surface variants together so
# short queries don't miss chunks on a plural/tense mismatch.
_SUFFIXES = ("ational", "tion", "ing", "ment", "ness", "able", "ed", "es", "ly", "s")


def _stem(word: str) -> str:
    for suf in _SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            return word[: -len(suf)]
    return word


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN_RE.findall(text.lower())]


class HybridIndex:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self._by_id = {c.chunk_id: c for c in chunks}
        self._bm25 = BM25Okapi([tokenize(c.text) for c in chunks]) if chunks else None
        self._embedder = get_embedder()
        self._dense = list(self._embedder.embed([c.text for c in chunks])) if chunks else []

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        return self._by_id.get(chunk_id)

    @classmethod
    def from_corpus_dir(cls, corpus_dir: Path) -> "HybridIndex":
        return cls(load_corpus(corpus_dir))

    def search(self, query: str, top_k: int = 5) -> list[tuple[Chunk, float]]:
        if not self.chunks:
            return []

        bm25_scores = self._bm25.get_scores(tokenize(query))
        bm25_rank = sorted(range(len(self.chunks)), key=lambda i: -bm25_scores[i])

        query_vec = next(self._embedder.embed([query]))
        dense_scores = [float(query_vec @ v) for v in self._dense]
        dense_rank = sorted(range(len(self.chunks)), key=lambda i: -dense_scores[i])

        # Reciprocal Rank Fusion, k=60 (standard RRF constant).
        k = 60
        fused: dict[int, float] = {}
        for rank, idx in enumerate(bm25_rank):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank)
        for rank, idx in enumerate(dense_rank):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank)

        ordered = sorted(fused.items(), key=lambda kv: -kv[1])[:top_k]
        return [(self.chunks[idx], score) for idx, score in ordered]
