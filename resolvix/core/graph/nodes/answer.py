"""answer: cache-hit short-circuit inside the graph; a genuinely fresh LLM answer is
generated OUTSIDE the compiled graph, by the shim (core/openai_shim/routes.py) —
see build.py's module docstring for why this node doesn't stream tokens itself.
"""
from resolvix.core.graph.state import SessionState


async def answer(state: SessionState) -> dict:
    if state.get("cache_hit_answer"):
        return {"outcome": state["cache_hit_answer"]}
    # No cache hit: outcome stays unset: the shim generates + streams the real
    # answer after this graph run completes, using the same decision/retrieval.
    return {"outcome": None}
