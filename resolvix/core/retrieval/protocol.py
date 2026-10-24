"""Retriever contract — one shape every domain pack's corpus resolves to."""
from typing import Protocol

from resolvix.core.retrieval.chunking import Chunk


class Retriever(Protocol):
    def search(self, query: str, top_k: int = 5) -> list[tuple[Chunk, float]]: ...
