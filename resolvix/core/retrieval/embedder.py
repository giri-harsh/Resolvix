"""Shared TextEmbedding singleton — HybridIndex and SemanticCache both used to load
their own copy of BAAI/bge-small-en-v1.5, doubling model-init cost and, worse,
happening lazily on the first live request (blocking the event loop for the whole
SSE response, discovered by an actual failing curl test — see app.py's startup
warmup for the other half of this fix).
"""
from fastembed import TextEmbedding

_embedder: TextEmbedding | None = None


def get_embedder() -> TextEmbedding:
    global _embedder
    if _embedder is None:
        _embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    return _embedder
