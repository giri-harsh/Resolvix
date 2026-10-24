"""cache_probe: semantic cache lookup, runs concurrently with retrieve/classify (§9.2 5a)."""
from resolvix.core.graph.state import SessionState
from resolvix.core.retrieval.semantic_cache import SemanticCache

_caches: dict[str, SemanticCache] = {}


def _cache_for(domain: str) -> SemanticCache:
    if domain not in _caches:
        _caches[domain] = SemanticCache()
    return _caches[domain]


async def cache_probe(state: SessionState) -> dict:
    cache = _cache_for(state["domain"])
    hit = cache.probe(state["current_utterance"])
    return {"cache_hit_answer": hit}
