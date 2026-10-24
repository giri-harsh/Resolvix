"""retrieve: hybrid search over the active domain's corpus (§9.2 row 5b)."""
from resolvix.core.domain.loader import get_pack
from resolvix.core.graph.state import RetrievalTrace, SessionState
from resolvix.core.telemetry.spans import span


async def retrieve(state: SessionState) -> dict:
    pack = get_pack(state["domain"])
    retriever = pack.retriever()
    with span("retrieve"):
        results = retriever.search(state["current_utterance"], top_k=5)

    trace = RetrievalTrace(
        chunk_ids=[c.chunk_id for c, _ in results],
        scores=[s for _, s in results],
        queues=[c.queue for c, _ in results],
        lexical_ms=0,
        dense_ms=0,
    )
    return {"last_retrieval": trace}
